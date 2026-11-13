# Whole-genome reference admission

Admitted on 11 November 2026 for the first simulated Standard baseline. These
inputs define exact simulation truth from frozen published sequences. Admission
does not establish independent biological ground truth for a later real isolate,
and this two-reference baseline does not admit the complete five-group panel.

| Reference ID | Frozen source and molecule | Native inventory | Measured length | Measured GC |
| --- | --- | --- | ---: | ---: |
| `bsub-168-whole` | RefSeq assembly `GCF_000009045.1`, chromosome `NC_000964.3`; independently matched GenBank alias `AL009126.3` | One circular chromosome | 4,215,606 bp | 43.514408% |
| `llactis-il1403-whole` | Original GenBank assembly `GCA_000006865.1`, chromosome `AE005176.1`; independently matched RefSeq alias `NC_002662.1` | One circular chromosome | 2,365,589 bp | 35.329383% |

Both payloads contain only A, C, G and T: their measured ambiguous-base counts
are zero. GC is recomputed from the actual admitted sequence bytes, rather than
copied from rounded publication figures. The two genomes are initial baseline
inputs; differences between them cannot isolate a causal GC effect.

## What was checked

For each reference, the exact assembly directory supplied genomic FASTA,
GenBank, assembly report and assembly statistics files. These four primary
payloads were checked against the publisher's MD5 index, then frozen with SHA256.
The checksum index and independently fetched alias FASTA were also SHA256-bound.
The admission also checked:

- Exactly one source FASTA record and one GenBank record.
- Accession versions and chromosome lengths agree with the assembly report.
- Native circularity is explicitly recorded in the GenBank `LOCUS` line.
- The complete FASTA sequence equals the GenBank `ORIGIN` sequence.
- An independently downloaded counterpart-assembly FASTA has the expected alias
  and exactly the same sequence.
- Molecule sequence hashes, lengths, GC counts and ambiguity counts match the
  declared inventory.

The *B. subtilis* assembly report has two rows representing GenBank and RefSeq
aliases. Those rows are not two biological molecules. Independent sequence
comparison resolves both to the single chromosome represented in the FASTA and
GenBank files.

The original IL1403 reference was retained. It was not replaced by the later
`CP033607` resequencing accession. [NCBI BioProject PRJNA72](https://www.ncbi.nlm.nih.gov/bioproject/72)
identifies the original plasmid-free laboratory derivative and its complete
assembly. No plasmid inventory is inferred for any other isolate.

## Canonical representation and receipts

Preparation keeps the full native sequence, original molecule accession and
source molecule order. It adds a `circular=true` FASTA header annotation for the
simulator and wraps uppercase DNA at 80 bases. There is no slicing, coordinate
rotation or sequence editing. The canonical FASTA hash is separately recorded
from the compressed and decompressed source hashes.

- [`bsub-168-whole` admission receipt](../assets/admissions/bsub-168-whole.json)
- [`llactis-il1403-whole` admission receipt](../assets/admissions/llactis-il1403-whole.json)
- [Admitted reference registry](../assets/references.json)

Each receipt binds source URLs, publisher checksums, payload hashes, canonical
FASTA hash, the exact molecule inventory, topology evidence and attribution.
Registry entries bind the receipt file's SHA256. Raw source archives are cached
by the common preparation program under `<cache_dir>/references/archives/`;
supporting original metadata remain in the admission receipts. Cache files are
outside Git. The original admission directory layout is historical evidence.

The existing `bsub-168-quick` entry and its 200 kb linear fixture remain unchanged
and separate from the admitted whole chromosome.

## Attribution and data usage

The *B. subtilis* source records cite [Barbe et al. (2009)](https://doi.org/10.1099/mic.0.027839-0)
and [Belda et al. (2013)](https://pubmed.ncbi.nlm.nih.gov/23429746/). The original
IL1403 genome is described by [Bolotin et al. (2001)](https://doi.org/10.1101/gr.169701).
Versioned accessions and the source assembly metadata are retained alongside
these publications.

Receipts record [NCBI's molecular data usage policy](https://www.ncbi.nlm.nih.gov/home/about/policies/).
NCBI itself does not impose reuse or redistribution restrictions on its molecular
database data, while it does not transfer third-party rights. No dataset-specific
Creative Commons or public-domain licence is asserted here.

The remaining *Micrococcus luteus* and WCFS1 candidates are still proposals.
WCFS1's corrected chromosome/native-plasmid compatibility requires a separate
admission; neither candidate is silently included in this baseline.
