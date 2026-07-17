// ============================================================================
// Neo4j ingestion + analyst queries for the temporal multiplex graph
// Graph JSON shape: {"nodes": [...], "edges": [...]} (see pipeline/models.py)
//
// Conventions:
//   - Node label   :Criminal, keyed by unique node_id
//   - Rel type     = multiplex layer (IDEOLOGICAL | FINANCIAL |
//                    PRISON_CO_LOCATION | TRANSNATIONAL)
//   - Every rel has confidence (EXTRACTED/INFERRED/AMBIGUOUS), derived weight
//     (1.0/0.7/0.4), start_date, end_date (null = ongoing), and provenance.
// ============================================================================

// ---- 0. Constraint (run once) ----------------------------------------------
CREATE CONSTRAINT criminal_node_id IF NOT EXISTS
FOR (c:Criminal) REQUIRE c.node_id IS UNIQUE;

// ---- 1. Node ingest (parameterized: pass $nodes = graph.json "nodes" array) -
UNWIND $nodes AS n
MERGE (c:Criminal {node_id: n.node_id})
SET c.name = n.name,
    c.aliases = n.aliases,
    c.nic = n.nic,
    c.affiliations = n.affiliations,
    c.node_type = n.node_type,
    c.cluster_id = n.cluster_id,
    c.source_file = n.source_file,
    c.source_excerpt = n.source_excerpt;

// ---- 2a. Edge ingest with APOC (dynamic relationship type from e.layer) -----
// Pass $edges = graph.json "edges" array. Requires the APOC plugin.
UNWIND $edges AS e
MATCH (a:Criminal {node_id: e.source})
MATCH (b:Criminal {node_id: e.target})
CALL apoc.merge.relationship(
  a,
  e.layer,                                                    // rel type = layer
  {relation: e.relation, source_file: coalesce(e.source_file, '')},  // identity props
  {},                                                         // onCreate props (set below)
  b,
  {}
) YIELD rel
SET rel.confidence = e.confidence,
    rel.weight = e.weight,
    rel.start_date = CASE WHEN e.start_date IS NULL THEN null ELSE date(e.start_date) END,
    rel.end_date   = CASE WHEN e.end_date   IS NULL THEN null ELSE date(e.end_date)   END,
    rel.location = e.location,
    rel.extraction_method = e.extraction_method,
    rel.source_excerpt = e.source_excerpt;

// ---- 2b. Edge ingest WITHOUT APOC (fixed :LINKED type, layer as a property) --
// Use this variant on a vanilla server. Note: pipeline/neo4j_export.py avoids
// the limitation entirely by batching per layer with real relationship types.
UNWIND $edges AS e
MATCH (a:Criminal {node_id: e.source})
MATCH (b:Criminal {node_id: e.target})
MERGE (a)-[r:LINKED {relation: e.relation, layer: e.layer,
                     source_file: coalesce(e.source_file, '')}]->(b)
SET r.confidence = e.confidence,
    r.weight = e.weight,
    r.start_date = CASE WHEN e.start_date IS NULL THEN null ELSE date(e.start_date) END,
    r.end_date   = CASE WHEN e.end_date   IS NULL THEN null ELSE date(e.end_date)   END,
    r.location = e.location,
    r.extraction_method = e.extraction_method,
    r.source_excerpt = e.source_excerpt;

// ============================================================================
// ANALYST QUERIES
// ============================================================================

// ---- Q1. Snapshot of the network as of a given date ($asOf, e.g. date("2023-06-15"))
//          A relationship is "active" if it started on/before $asOf and has not ended.
MATCH (a:Criminal)-[r]->(b:Criminal)
WHERE r.start_date IS NOT NULL
  AND r.start_date <= $asOf
  AND (r.end_date IS NULL OR r.end_date >= $asOf)
RETURN a.name, type(r) AS layer, r.relation, r.confidence, r.weight, b.name,
       r.start_date, r.end_date
ORDER BY r.weight DESC;

// ---- Q2. Single-layer projection (e.g. the FINANCIAL layer only)
MATCH (a:Criminal)-[r:FINANCIAL]->(b:Criminal)
RETURN a.name, r.relation, r.weight, r.start_date, r.end_date, b.name;

// ---- Q3. Hard facts only: filter out anything below EXTRACTED
MATCH (a:Criminal)-[r]->(b:Criminal)
WHERE r.confidence = 'EXTRACTED'
RETURN a.name, type(r) AS layer, r.relation, b.name, r.source_file;

// ---- Q4. Review queue: AMBIGUOUS edges an analyst should confirm or discard
MATCH (a:Criminal)-[r]->(b:Criminal)
WHERE r.confidence = 'AMBIGUOUS'
RETURN a.name, type(r) AS layer, r.relation, b.name, r.source_excerpt, r.source_file;

// ---- Q5. Confidence-weighted paths between two persons of interest
//          Path score = product of edge weights; low scores = speculative chains.
MATCH p = (a:Criminal {node_id: $from})-[*..4]-(b:Criminal {node_id: $to})
WITH p, reduce(s = 1.0, r IN relationships(p) | s * r.weight) AS path_confidence
RETURN [n IN nodes(p) | n.name] AS chain,
       [r IN relationships(p) | type(r)] AS layers,
       round(path_confidence, 3) AS path_confidence
ORDER BY path_confidence DESC
LIMIT 10;

// ---- Q6. Detected cells (Leiden cluster_id written by pipeline/clustering.py)
MATCH (c:Criminal)
RETURN c.cluster_id AS cell, count(*) AS size, collect(c.name) AS members
ORDER BY cell;

// ---- Q7. Cross-layer brokers: people active on 2+ layers (multiplex bridges)
MATCH (c:Criminal)-[r]-()
WITH c, collect(DISTINCT type(r)) AS layers
WHERE size(layers) >= 2
RETURN c.name, layers, size(layers) AS layer_count
ORDER BY layer_count DESC;

// ---- Q8. Ongoing relationships right now (end_date is null)
MATCH (a:Criminal)-[r]->(b:Criminal)
WHERE r.end_date IS NULL AND r.start_date IS NOT NULL
RETURN a.name, type(r) AS layer, r.relation, b.name, r.start_date, r.confidence;
