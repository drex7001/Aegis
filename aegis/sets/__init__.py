"""Object sets: a saved, versioned, shareable filter tree over objects (spec 12).

> A set is a **question**, not an answer. It stores a query, never results, and
> it grants nothing.

| Module | Responsibility |
|---|---|
| `grammar` | the AST, its validation against the ontology, and interface pinning |
| `limits` | the complexity numbers B-17 asks for, enforced at **save** |
| `compile` | the only place a set becomes SQL, and it is always parameterized |

The two rules that shape all three: a definition can hold no SQL because there
is no free-text field for it to hide in, and a definition can hold no results
because there is nowhere in the schema to put them.
"""
