"""Mirror engine orchestrator: fetch → transform → load, in dependency order."""

import logging

from src.ingestion.resource_fetcher import ResourceFetcher
from src.ingestion.resources import ordered_resources
from src.loading.resource_loader import ResourceLoader

logger = logging.getLogger(__name__)


def run_mirror(
    only: list[str] | None = None,
    fetcher: ResourceFetcher | None = None,
    loader: ResourceLoader | None = None,
    expand_deps: bool = True,
) -> dict[str, int]:
    """Mirror PokéAPI resources into the local database.

    Args:
        only: resource names to mirror (transitive deps auto-included unless
            expand_deps is False). None mirrors the whole registry.
        expand_deps: include transitive dependencies of `only` (CLI default).

    Returns:
        Mapping of resource name -> rows loaded.
    """
    fetcher = fetcher or ResourceFetcher()
    loader = loader or ResourceLoader()

    specs = ordered_resources(only, expand_deps=expand_deps)
    logger.info(f"Mirroring {len(specs)} resources in order: {[s.name for s in specs]}")

    totals: dict[str, int] = {}
    for spec in specs:
        skipped = 0  # records dropped because transform/shaping raised (best-effort)

        if spec.mode == "jsonb":
            rows = []
            for raw in fetcher.fetch_all(spec.name):
                try:
                    rows.append({"id": raw["id"], "name": raw.get("name"), "data": raw})
                except Exception as e:
                    skipped += 1
                    logger.error(f"Skipping malformed {spec.name} record: {e}")
            loader.load_jsonb(spec.name, rows)
            totals[spec.name] = len(rows)

        elif spec.tables:
            # Fan-out: aggregate every record's rows per table, then upsert each
            # table in declared order (parents before junctions).
            if spec.transform is None:
                raise ValueError(f"fan-out spec '{spec.name}' has no transform")
            aggregated: dict[str, list[dict]] = {ts.key: [] for ts in spec.tables}
            count = 0
            for raw in fetcher.fetch_all(spec.name):
                try:
                    out = spec.transform(raw)
                except Exception as e:
                    skipped += 1
                    logger.error(f"Skipping malformed {spec.name} record: {e}")
                    continue
                for key, rows in out.items():
                    aggregated.setdefault(key, []).extend(rows)
                count += 1
            # Load all tables of the resource in one transaction (all-or-nothing):
            # a child-table failure must not leave a half-loaded parent.
            for ts in spec.tables:
                loader.load_relational(
                    ts.model, aggregated.get(ts.key, []), conflict_cols=ts.conflict, commit=False
                )
            loader.commit()
            totals[spec.name] = count

        else:
            transform, model = spec.transform, spec.model
            if transform is None or model is None:  # registry invariant
                raise ValueError(f"relational spec '{spec.name}' missing transform/model")
            rows = []
            for raw in fetcher.fetch_all(spec.name):
                try:
                    rows.append(transform(raw))
                except Exception as e:
                    skipped += 1
                    logger.error(f"Skipping malformed {spec.name} record: {e}")
            loader.load_relational(model, rows)
            totals[spec.name] = len(rows)

        if skipped:
            logger.warning(f"{spec.name}: {skipped} record(s) skipped (malformed)")

    logger.info(f"Mirror complete: {sum(totals.values())} records across {len(totals)} resources")
    return totals
