"""Streamlit dashboard for Pokémon data visualization."""

import logging
from uuid import uuid4

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.analytics.stats_analyzer import StatsAnalyzer
from src.analytics.type_analyzer import TypeAnalyzer
from src.models.base import session_scope

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Pokémon Data Analytics Dashboard", page_icon="🐉", layout="wide")


def _generation_label(name: str | None) -> str:
    if name is None:
        return "Unknown generation"
    return f"Generation {name.removeprefix('generation-').upper()}"


def get_pokemon_options(db: Session) -> pd.DataFrame:
    """Assign forms to the debut generation of their species."""
    rows = (
        db.execute(
            text("""
            SELECT p.id, p.name, s.generation_id, g.name AS generation_name
            FROM pokemon p
            LEFT JOIN pokemon_species s ON s.id = p.species_id
            LEFT JOIN generations g ON g.id = s.generation_id
            WHERE NOT EXISTS (
                SELECT 1 FROM api_resource ar
                WHERE ar.resource_type = 'pokemon' AND ar.id = p.id AND ar.is_present = false
            )
            ORDER BY p.id
        """)
        )
        .mappings()
        .all()
    )
    return pd.DataFrame(rows, columns=["id", "name", "generation_id", "generation_name"])


def _data_table(data: pd.DataFrame) -> None:
    st.dataframe(data, width="stretch", hide_index=True)


def get_mirror_status(db: Session) -> list[dict]:
    """Return latest attempt and last complete success for each dashboard resource."""
    rows = (
        db.execute(
            text("""
            WITH ranked AS (
                SELECT resource_type, status, completed_at, failed,
                       ROW_NUMBER() OVER (
                           PARTITION BY resource_type
                           ORDER BY completed_at DESC, started_at DESC, run_id DESC
                       ) AS recency
                FROM mirror_resource_runs
                WHERE resource_type IN ('pokemon', 'type')
            )
            SELECT resource_type,
                   MAX(CASE WHEN recency = 1 THEN status END) AS latest_status,
                   MAX(CASE WHEN recency = 1 THEN completed_at END) AS latest_attempt,
                   MAX(CASE WHEN recency = 1 THEN failed END) AS latest_failed,
                   MAX(CASE WHEN status = 'success' THEN completed_at END) AS last_success
            FROM ranked
            GROUP BY resource_type
            ORDER BY resource_type
        """)
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def _mirror_status(db: Session) -> list[dict]:
    status_rows = get_mirror_status(db)
    if not status_rows:
        st.info("No completed Pokémon or type mirror run is recorded yet.")
        return status_rows
    for row in status_rows:
        resource = row["resource_type"].capitalize()
        last_success = row["last_success"] or "none recorded"
        st.caption(f"{resource}: last successful mirror {last_success}")
        if row["latest_status"] != "success":
            st.warning(
                f"Latest {resource.lower()} mirror attempt {row['latest_status']} "
                f"at {row['latest_attempt']}; {row['latest_failed']} records failed. "
                "Displayed data may be older or incomplete."
            )
    return status_rows


@st.cache_data(show_spinner=False)
def _cached_effectiveness_matrix(last_success: str) -> pd.DataFrame:
    """Cache complete type data until its successful mirror marker changes."""
    with session_scope() as db:
        return TypeAnalyzer(db_session=db).get_effectiveness_matrix()


def _matrix_for(types: TypeAnalyzer, status_rows: list[dict] | None = None) -> pd.DataFrame:
    type_run = next((row for row in (status_rows or []) if row["resource_type"] == "type"), None)
    if type_run and type_run["latest_status"] == "success" and type_run["last_success"]:
        return _cached_effectiveness_matrix(str(type_run["last_success"]))
    return types.get_effectiveness_matrix()


def _stats_page(stats: StatsAnalyzer) -> None:
    st.header("Top Pokémon by Base Stats")
    top = stats.get_top_pokemon_by_total_base_stats(limit=10)
    if top.empty:
        st.info("No Pokémon stats yet. Run a successful Pokémon mirror to populate this analysis.")
    else:
        fig = px.bar(
            top,
            x="name",
            y="total_base_stats",
            labels={"name": "Pokémon", "total_base_stats": "Total Base Stats"},
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, width="stretch")
        st.subheader("Base stats data")
        _data_table(top)

    st.subheader("Move type diversity")
    version_rows = stats.db.execute(
        text("SELECT id, name FROM version_groups ORDER BY order_num, id")
    ).all()
    version_names = {row[0]: row[1] for row in version_rows}
    version_options = [None, *version_names]
    selected_version = st.selectbox(
        "Version group for move coverage",
        options=version_options,
        format_func=lambda value: (
            "All version groups (union)" if value is None else version_names[value]
        ),
    )
    if selected_version is None:
        st.caption(
            "Each move counts once across the union of known and legacy unscoped games. "
            "Type coverage is the share of available move types, not damage coverage."
        )
    else:
        st.caption(
            "Only moves recorded for this version group count. Legacy moves without "
            "version provenance are excluded. Type coverage measures move type diversity."
        )
    coverage = stats.get_pokemon_with_best_type_coverage(
        limit=10, version_group_id=selected_version
    )
    if coverage.empty:
        st.info("No move coverage yet. Mirror Pokémon and moves to populate this analysis.")
    else:
        coverage = coverage.copy()
        coverage["type_coverage"] = coverage["type_coverage_ratio"].map(
            lambda ratio: f"{float(ratio) * 100:.1f}%" if pd.notna(ratio) else "Unknown"
        )
        _data_table(coverage.drop(columns="type_coverage_ratio"))


def _distribution_page(stats: StatsAnalyzer) -> None:
    st.header("Type Distribution")
    st.caption("Counts are type memberships; a Pokémon with two types contributes to both.")
    distribution = stats.get_type_distribution()
    if distribution.empty:
        st.info("No Pokémon types yet. Mirror Pokémon and types to populate this analysis.")
    else:
        fig = px.pie(distribution, names="type_name", values="pokemon_count")
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, width="stretch")
        st.subheader("Type membership data")
        _data_table(distribution)

    st.subheader("Dual-type combinations")
    combinations = stats.get_dual_type_combinations()
    if combinations.empty:
        st.info("No dual-type combinations available.")
    else:
        _data_table(combinations)


def _effectiveness_page(types: TypeAnalyzer, status_rows: list[dict] | None = None) -> None:
    st.header("Type Effectiveness")
    matrix = _matrix_for(types, status_rows)
    if matrix.empty:
        st.info("No types yet. Mirror types to populate the effectiveness matrix.")
        return

    st.caption("Rows attack columns. 1× is neutral, 2× is super effective, and 0× is immune.")
    st.subheader("Explore one attacking type")
    attacking_type = st.selectbox("Attacking type", options=matrix.index.tolist())
    selected = pd.DataFrame(
        {
            "defending_type": matrix.columns,
            "effectiveness": matrix.loc[attacking_type].values,
        }
    )
    _data_table(selected)

    st.subheader("Effectiveness matrix")
    fig = px.imshow(
        matrix,
        labels={"x": "Defending type", "y": "Attacking type", "color": "Multiplier"},
        x=matrix.columns.tolist(),
        y=matrix.index.tolist(),
        color_continuous_scale="RdYlGn",
        aspect="auto",
    )
    fig.update_layout(height=max(650, len(matrix) * 35))
    st.plotly_chart(fig, width="stretch")

    st.subheader("Complete effectiveness data")
    st.caption("The scrollable table gives every attacking and defending combination in text.")
    _data_table(matrix.rename_axis("attacking_type").reset_index())

    st.subheader("Best attacking types")
    _data_table(types.find_best_attacking_types(matrix))
    st.subheader("Best defensive types")
    _data_table(types.find_best_defensive_types(matrix))


def _pokemon_page(db: Session, types: TypeAnalyzer, status_rows: list[dict] | None = None) -> None:
    st.header("Individual Pokémon Analysis")
    pokemon = get_pokemon_options(db)
    if pokemon.empty:
        st.info("No Pokémon yet. Run a successful Pokémon mirror to start this analysis.")
        return

    generation_labels = {
        int(row.generation_id): _generation_label(row.generation_name)
        for row in pokemon.itertuples()
        if pd.notna(row.generation_id)
    }
    options = ["All generations"] + [generation_labels[key] for key in sorted(generation_labels)]
    if pokemon["generation_id"].isna().any():
        options.append("Unknown generation")
    selected_generation = st.selectbox("Filter by species debut generation", options=options)
    if selected_generation == "Unknown generation":
        pokemon = pokemon[pokemon["generation_id"].isna()]
    elif selected_generation != "All generations":
        selected_id = next(
            key for key, label in generation_labels.items() if label == selected_generation
        )
        pokemon = pokemon[pokemon["generation_id"] == selected_id]
    if pokemon.empty:
        st.info("No Pokémon found for this generation.")
        return

    names = dict(zip(pokemon["id"], pokemon["name"], strict=True))
    pokemon_id = st.selectbox(
        "Select a Pokémon to analyze",
        options=list(names),
        format_func=lambda value: f"#{value} - {names[value]}",
    )
    matrix = _matrix_for(types, status_rows)
    profile = types.get_pokemon_weakness_profile(pokemon_id, matrix)
    st.subheader("Type effectiveness against this Pokémon")
    if profile.empty:
        st.info("No weakness profile available. Mirror types and Pokémon type memberships.")
        return
    fig = px.bar(
        profile,
        x="attacking_type",
        y="effectiveness",
        labels={"attacking_type": "Attacking type", "effectiveness": "Multiplier"},
    )
    fig.update_layout(xaxis_tickangle=-45)
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, width="stretch")
    st.subheader("Complete weakness profile")
    _data_table(profile)

    st.subheader("Recommended counter types")
    counters = types.recommend_counter_types(pokemon_id, weakness_profile=profile)
    if counters.empty:
        st.info("No super-effective counter types found for this Pokémon.")
    else:
        _data_table(counters)


def main() -> None:
    """Render only the selected analysis with a session scoped to this rerun."""
    st.title("Pokémon Data Analytics Dashboard")
    st.caption("Explore species, forms, stats, and type matchups")
    selected_page = st.selectbox(
        "Analysis view",
        options=[
            "Top Pokémon Stats",
            "Type Distribution",
            "Type Effectiveness",
            "Pokémon Analyzer",
        ],
    )
    try:
        with session_scope() as db:
            status_rows = _mirror_status(db)
            stats = StatsAnalyzer(db_session=db)
            types = TypeAnalyzer(db_session=db)
            if selected_page == "Pokémon Analyzer":
                _pokemon_page(db, types, status_rows)
            elif selected_page == "Type Effectiveness":
                _effectiveness_page(types, status_rows)
            elif selected_page == "Type Distribution":
                _distribution_page(stats)
            else:
                _stats_page(stats)
    except SQLAlchemyError:
        diagnostic_id = uuid4().hex[:12]
        logger.exception("Dashboard database error (reference %s)", diagnostic_id)
        st.error(
            "The data is temporarily unavailable. Check the database connection and try again. "
            f"Reference: {diagnostic_id}"
        )
        if st.button("Retry connection"):
            st.rerun()


if __name__ == "__main__":
    main()
