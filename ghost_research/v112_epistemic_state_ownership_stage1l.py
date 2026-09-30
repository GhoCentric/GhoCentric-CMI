from copy import deepcopy

LIVE_FIELDS = (
    "_tick",
    "_sequence",
    "_records",
    "_by_id",
    "_facts",
    "_beliefs",
    "_latest",
)

PERSISTED_FIELDS = (
    "tick",
    "sequence",
    "records",
)


def authoritative_projection(snapshot):
    return {
        "schema_version": snapshot["schema_version"],
        "tick": snapshot["tick"],
        "sequence": snapshot["sequence"],
        "records": deepcopy(snapshot["records"]),
    }


def rebuild_indexes(records):
    by_id = {}
    facts = {}
    beliefs = {}
    latest = {}

    for source in records:
        record = deepcopy(source)
        record_id = record["id"]
        by_id[record_id] = record

        if record["kind"] == "fact":
            facts[record["fact_id"]] = record
        elif record["kind"] == "belief":
            beliefs[record_id] = record
            latest[(record["holder"], record["subject"])] = record_id

    return {
        "by_id": by_id,
        "facts": facts,
        "beliefs": beliefs,
        "latest": latest,
    }


def ownership_summary(snapshot):
    indexes = rebuild_indexes(snapshot["records"])
    return {
        "persisted_runtime_fields": list(PERSISTED_FIELDS),
        "derived_index_names": ["by_id", "facts", "beliefs", "latest"],
        "record_count": len(snapshot["records"]),
        "fact_index_count": len(indexes["facts"]),
        "belief_index_count": len(indexes["beliefs"]),
        "latest_belief_count": len(indexes["latest"]),
    }
