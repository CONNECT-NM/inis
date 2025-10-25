# INIS CONNECT-NM SKOS Version
A SKOS RDF version of the 2018 INIS Thesaurus to be used as reference to the CONNECT-NM projects.



# INIS 2018 PDF to SKOS Conversion Rules

## Conversion Workflow Summary

### 1. Input

A textual version of the **IAEA INIS Thesaurus** containing:

- Alphabetically ordered descriptor blocks
- A single `<bold>Term</bold>` descriptor per block
- Optional introduction dates after the descriptor
- Optional definition text
- Optional parenthetical comments
- Relationship lists using controlled codes:
  - `UF` / `SF` → alternate labels
  - `BT`, `NT`, `RT` → hierarchical or associative relationships
  - `USE` / `SEE` → redirections (non-preferred terms)

### 2. Parsing Logic

#### Block Structure Recognition

The parser:

- Detects each descriptor by `<bold>…</bold>`
- Associates all following lines to that descriptor block until the next `<bold>`
- Dates are parsed according to INIS/ETDE rules:
  - One bare date → introduced in both systems
  - Two labeled dates → separate `inis:introducedINIS` and `inis:introducedETDE`
  - No dates → assumed pre-1975 (left unassigned)

#### Definition and Comments

- Continuous text before relationships → `skos:definition`
- Parentheses text anywhere in the block → `skos:historyNote` (parentheses removed)
- Free-text correctly spanned across multiple lines

#### Controlled Relationship Mapping

| Source pattern   | Semantic meaning                         | SKOS mapping                                                 |
| ---------------- | ---------------------------------------- | ------------------------------------------------------------ |
| `UF` or `SF`     | Synonym controlled by current descriptor | `skos:altLabel`                                              |
| `BT`, `NT`, `RT` | Broader, Narrower, Related               | `skos:broader`, `skos:narrower`, `skos:related`              |
| `USE`, `SEE`     | Redirection to another descriptor        | Source term becomes an `skos:altLabel` of target (no concept created) |

✅ Multi-line continuation for each relationship supported

A second pass ensures hierarchical symmetry:

- `A skos:broader B` → `B skos:narrower A`

------

### 3. JSON-LD SKOS Output Construction

All valid descriptors were serialized as:

- `skos:Concept` with URI pattern `inis:<slugified_label>`
- `skos:prefLabel`, `skos:altLabel`, definitions, notes, relations
- Custom date properties:
  - `inis:introducedINIS` and `inis:introducedETDE` with datatype `xsd:date`
- Concept scheme: `inis:scheme` (`skos:ConceptScheme`)

Result: ~22,650 concepts successfully generated

------

### 4. Transformation to OWL 2 DL Ontology (Turtle)

#### Semantic Enrichment

- Ontology IRI: `http://purl.org/connect-nm/inis`
- Import of **SKOS Core**
- Prefix structure declared for OWL, SKOS, DCTERMS, FOAF, XSD, etc.

#### Top-concept Identification

Rule: any concept **without** a `skos:broader` link

- Annotated as:
  - `skos:topConceptOf inis:scheme`
  - `inis:scheme skos:hasTopConcept`

#### Property Hierarchy Enhancement

- `inis:introducedINIS` ⊑ `dcterms:created`
- `inis:introducedETDE` ⊑ `dcterms:created`

#### Concept Scheme Metadata from INIS Thesaurus 2018 PDF

Extracted from front-matter:

- Title, Publisher, Place (Vienna)
- Issue date normalized to `2018-02-01`
- Series and publication identifier
- Short description from Preface
- Language (`en`)

Final ontology document:

- ~22K `skos:Concept` individuals
- ~3.5K `skos:topConcept` entries
- Robust metadata for FAIR usage

------

## Output Summary

| Output Stage     | Format                       | Purpose                                              |
| ---------------- | ---------------------------- | ---------------------------------------------------- |
| Parsed thesaurus | Internal Python object model | Semantic extraction                                  |
| SKOS Vocabulary  | JSON-LD                      | Interoperable linked data                            |
| Final Ontology   | OWL 2 DL (Turtle)            | Reasonable, metadata-enriched, SKOS-aligned ontology |

------

