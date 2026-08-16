# 001 — The ontology becomes a composition of modules

- **Bump**: `1.2.0` → `1.3.0` (`minor`)
- **Modules**: `platform` → `1.0.0` (new), `criminal_network` → `1.0.0` (new)
- **Task / ADR**: T30, ADR-037

> Backfilled by T35, which built the proposal workflow. The change it describes
> landed at T30; writing it afterwards is the honest way to start the chain,
> and it is the only proposal in this directory that is retrospective.

## Motivation

Article XIV says the core is domain-neutral and domains arrive as ontology
modules. Nothing enforced it. `ontology/aegis.yaml` was one flat file mixing
governance vocabulary — handling codes, grading, source types, the actions a
human may take — with criminal-network vocabulary: five object types and
thirty-three predicates about people and organizations.

The consequence was not stylistic. "Domains are modules" was a claim no test
could fail, so there was no way to know whether adding a second domain would
require code changes until someone tried.

## Competency questions (GOAL.md §7.9)

1. Which module declares this predicate, and may another module reference it?
2. What would a second analytical domain have to replace, and what would it
   inherit unchanged?
3. Which vocabulary is governance (true whatever the domain) and which is
   criminal-network specific?
4. Can a domain module widen the claim envelope, lower a handling floor, or
   invent a write path? (No — those live in `platform`.)

## Diff

`ontology/aegis.yaml` becomes a composition manifest; its sections move
unchanged into two module files.

```yaml
# ontology/aegis.yaml
version: 1.3.0
namespace: aegis.lk
composition:
  - {module: platform,         path: modules/platform.yaml,         version: "1.0.0"}
  - {module: criminal_network, path: modules/criminal-network.yaml, version: "1.0.0"}
```

```yaml
# ontology/modules/platform.yaml — handling_codes, source_types, grading, actions
module: {name: platform, namespace: aegis.lk/platform, version: 1.0.0}

# ontology/modules/criminal-network.yaml — object_types, predicates, categories
module:
  name: criminal_network
  namespace: aegis.lk/criminal-network
  version: 1.0.0
  imports:
    - {module: platform, version: ">=1.0.0,<2.0.0"}
```

## Compatibility

`minor`. Nothing was added, removed, renamed or retyped: the union of the two
module files is the previous file section for section, and the composed
registry is byte-identical under the §7.2 normalization. That equality is the
proof, not a claim about the diff.

Names stay **global and unprefixed** (ADR-037). `claim.predicate` is an
immutable TEXT column, so a lexical namespace would have meant rewriting
recorded rows or translating on every read — which would have made this a major
bump for no gain. A collision between two modules is a validation error instead.

`claim.ontology_version` continues to store the **composition** version, so
every value ever stamped keeps its meaning.

## Migration

Not applicable. No row changes, and no claim recorded under 1.2.0 or earlier
means anything different afterwards.
