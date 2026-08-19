# Module sources as of composition 1.7.0

Archived by T55 when composition **2.0.0** removed `location.precision`
(ADR-048). Spec 01 §4 requires a major bump to keep the sources it broke, and
`aegis ontology check-release` enforces it: the directory is named for the
version that *broke* them, not for the version they *are*.

These three files are `ontology/aegis.yaml`, `ontology/modules/platform.yaml`
and `ontology/modules/criminal-network.yaml` exactly as they stood at
composition 1.7.0 (platform 1.3.0, criminal_network 1.2.1). A claim stamped
`1.7.0` or earlier is interpreted against these, not against the live files.

The composed, module-resolved form of the same release is
`../composed-1.7.0.json`, which is what the compatibility diff reads. This
directory holds the *sources* — the comments explaining why each name is what
it is, which the composed JSON does not carry and which are the whole reason a
reader would come here.

Nothing here is loaded at runtime. Do not edit these files: an archive that
changes is not an archive.
