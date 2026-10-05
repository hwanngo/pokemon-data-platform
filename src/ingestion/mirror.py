"""Bounded, transactional PokéAPI mirror in dependency order."""

import json
import logging
import tempfile
from datetime import UTC, datetime
from uuid import uuid4

from src.ingestion.resource_fetcher import ResourceFetcher
from src.ingestion.resources import ordered_resources
from src.loading.resource_loader import ResourceLoader
from src.models.ability import PokemonAbility
from src.models.move import PokemonMove
from src.models.pokemon import PokemonStat
from src.models.type import PokemonType, TypeEffectiveness

logger = logging.getLogger(__name__)


class IncompleteMirrorError(RuntimeError):
    """A resource has missing or invalid details and cannot be published."""


def _source_timestamp(fetcher, name: str, ident: int) -> datetime | None:
    client = getattr(fetcher, "api_client", None)
    if client is None or not hasattr(client, "_get_cache_path"):
        return None
    path = client._get_cache_path(f"{name}/{ident}")
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return None


def run_mirror(
    only: list[str] | None = None,
    fetcher: ResourceFetcher | None = None,
    loader: ResourceLoader | None = None,
    expand_deps: bool = True,
    strict: bool = True,
    refresh: bool = True,
) -> dict[str, int]:
    """Mirror complete resources; each resource publishes in one transaction."""
    own_fetcher = fetcher is None
    own_loader = loader is None
    fetcher = fetcher or ResourceFetcher(refresh=refresh)
    loader = loader or ResourceLoader()
    totals: dict[str, int] = {}
    try:
        for spec in ordered_resources(only, expand_deps=expand_deps):
            started_at = datetime.now(UTC)
            run_id = str(uuid4())
            succeeded = 0
            failed_ids: list[int | str] = []
            type_edges: list[dict] = []
            successful_type_ids: set[int] = set()
            spool = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")  # noqa: SIM115 - closed in finally
            try:
                # Fetch before opening the publication transaction. Large
                # resources spill to disk instead of accumulating in RAM.
                for fetched in fetcher.fetch_all(spec.name):
                    ident = fetched.get("id") if isinstance(fetched, dict) else None
                    stamp = (
                        _source_timestamp(fetcher, spec.name, ident)
                        if isinstance(ident, int)
                        else None
                    )
                    spool.write(
                        json.dumps(
                            {
                                "raw": fetched,
                                "source_fetched_at": stamp.isoformat() if stamp else None,
                            }
                        )
                        + "\n"
                    )
                spool.seek(0)
                loader.begin_resource(spec.name, started_at)
                for line in spool:
                    record = json.loads(line)
                    raw = record["raw"]
                    ident = raw.get("id", "unknown") if isinstance(raw, dict) else "unknown"
                    try:
                        if not isinstance(raw, dict) or type(raw.get("id")) is not int:
                            raise ValueError("missing integer resource id")
                        ident = int(raw["id"])
                        out = spec.transform(raw) if spec.transform else None
                    except (KeyError, TypeError, ValueError) as exc:
                        failed_ids.append(ident)
                        logger.exception("Invalid %s/%s detail: %s", spec.name, ident, exc)
                        continue
                    if spec.mode != "jsonb" and spec.tables:
                        if not isinstance(out, dict):
                            raise TypeError(f"missing fan-out transform for {spec.name}")
                        if spec.name == "pokemon":
                            for model in (PokemonStat, PokemonType, PokemonAbility, PokemonMove):
                                loader.reconcile_children(model, "pokemon_id", ident)
                        for table in spec.tables:
                            if spec.name == "type" and table.key == "type_effectiveness":
                                type_edges.extend(out.get(table.key, []))
                                continue
                            loader.load_relational(
                                table.model, out.get(table.key, []), table.conflict, commit=False
                            )
                    elif spec.mode != "jsonb":
                        if spec.model is None or not isinstance(out, dict):
                            raise TypeError(f"missing relational transform/model for {spec.name}")
                        loader.load_relational(spec.model, [out], commit=False)
                    loader.load_jsonb(
                        spec.name,
                        [
                            {
                                "id": ident,
                                "name": raw.get("name"),
                                "data": raw,
                                "source_fetched_at": datetime.fromisoformat(
                                    record["source_fetched_at"]
                                )
                                if record["source_fetched_at"]
                                else None,
                            }
                        ],
                        commit=False,
                    )
                    succeeded += 1
                    if spec.name == "type":
                        successful_type_ids.add(ident)
                failed_ids.extend(getattr(fetcher, "failed_ids", []))
                attempted = getattr(fetcher, "attempted", 0) or succeeded + len(failed_ids)
                if strict and (failed_ids or attempted != succeeded or attempted == 0):
                    raise IncompleteMirrorError(
                        f"{spec.name}: {succeeded}/{attempted} details valid; failed IDs: {failed_ids[:25]}"
                    )
                if spec.name == "type":
                    # Targets may appear later in the list. Publish edges only
                    # after every type parent is present.
                    for attack_id in successful_type_ids:
                        loader.reconcile_children(TypeEffectiveness, "attack_type_id", attack_id)
                    loader.load_relational(
                        TypeEffectiveness,
                        type_edges,
                        ("attack_type_id", "defense_type_id"),
                        commit=False,
                    )
                listed_ids = getattr(fetcher, "listed_ids", None)
                if not failed_ids and listed_ids is not None:
                    loader.mark_absent(spec.name, listed_ids)
                loader.record_run(
                    run_id=run_id,
                    resource_type=spec.name,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                    status="success" if not failed_ids else "partial",
                    attempted=attempted,
                    succeeded=succeeded,
                    failed=len(failed_ids),
                    failed_ids=failed_ids,
                )
                loader.commit()
                totals[spec.name] = succeeded
            except Exception:
                loader.db.rollback()
                attempted = getattr(fetcher, "attempted", 0) or succeeded + len(failed_ids)
                failed_ids.extend(
                    i for i in getattr(fetcher, "failed_ids", []) if i not in failed_ids
                )
                try:
                    loader.record_run(
                        run_id=run_id,
                        resource_type=spec.name,
                        started_at=started_at,
                        completed_at=datetime.now(UTC),
                        status="failed",
                        attempted=attempted,
                        succeeded=succeeded,
                        failed=max(len(failed_ids), attempted - succeeded),
                        failed_ids=failed_ids,
                    )
                    loader.commit()
                except Exception:
                    loader.db.rollback()
                    logger.exception("Could not record failed %s run", spec.name)
                raise
            finally:
                spool.close()
        return totals
    finally:
        if own_loader:
            loader.close()
        if own_fetcher:
            fetcher.api_client.close()
