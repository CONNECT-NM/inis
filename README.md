# INIS CONNECT-NM SKOS Version
A SKOS RDF version of the 2018 INIS Thesaurus to be used as reference to the CONNECT-NM projects.



# INIS 2018 PDF to SKOS Conversion Rules

### 1. Controlled Relationship Mapping

| Source pattern   | Semantic meaning                         | SKOS mapping                                                 |
| ---------------- | ---------------------------------------- | ------------------------------------------------------------ |
| `UF` or `SF`     | Synonym controlled by current descriptor | `skos:altLabel`                                              |
| `BT`, `NT`, `RT` | Broader, Narrower, Related               | `skos:broader`, `skos:narrower`, `skos:related`              |
| `USE`, `SEE`     | Redirection to another descriptor        | Source term becomes an `skos:altLabel` of target (no concept created) |

- `A skos:broader B` → `B skos:narrower A`

------

### 2. JSON-LD SKOS Output Construction

All valid descriptors were serialized as:

- `skos:Concept` with URI pattern `inis:<slugified_label>`
- `skos:prefLabel`, `skos:altLabel`, definitions, notes, relations
- Custom date properties:
  - `inis:introducedINIS` and `inis:introducedETDE` with datatype `xsd:date`
- Concept scheme: `inis:scheme` (`skos:ConceptScheme`)

------

### 3. Transformation to OWL 2 DL Ontology (Turtle)

#### Semantic Enrichment

- Ontology IRI: `http://purl.org/connect-nm/inis`
- Import of **SKOS Core**
- Prefix structure declared for OWL, SKOS, DCTERMS, FOAF, XSD, etc.

#### Top-concept Identification

Rule: any concept **without** a `skos:broader` link

- Annotated as:
  - `skos:topConceptOf inis:scheme`
  - `inis:scheme skos:hasTopConcept`

Final ontology document:
- ~22K `skos:Concept` individuals
- ~3.5K `skos:topConcept` entries
- Robust metadata for FAIR usage

------

## Output Summary

| Output           | Format                       | Purpose                                              |
| ---------------- | ---------------------------- | ---------------------------------------------------- |
| SKOS Vocabulary  | JSON-LD                      | Interoperable linked data                            |
| Final Ontology   | OWL 2 DL (Turtle)            | Reasonable, metadata-enriched, SKOS-aligned ontology |

------

