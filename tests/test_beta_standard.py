"""Independent read reconstruction, exact budgets and executable beta selection."""
import json
from pathlib import Path
import tempfile
import unittest

from benchlib.io import fastq_records
from benchlib.planning import build_plan
from benchlib.standard_reads import budget, sample_records, simulate_standard

ROOT = Path(__file__).resolve().parents[1]


class BetaStandardTests(unittest.TestCase):
    def test_plan_budget_and_shared_comparators(self):
        plan = build_plan(ROOT, preset='standard')
        self.assertEqual(plan['expected_slots'],110)
        self.assertEqual(len(plan['reference_ids']),5)
        self.assertEqual({c['seed'] for c in plan['cases']},{101,202,303,404,505})
        plasmids = build_plan(ROOT,preset='standard',groups='plasmids')
        self.assertEqual(len(plasmids['cases']),15)
        self.assertEqual(len({c['id'] for c in plasmids['cases']}),15)

    def test_native_plasmid_cap_exact_budgets_and_coordinate_reconstruction(self):
        sequences={'CHR.1':'AACCGT'*1000,'PL.1':'AGTCC'*17}
        case={'id':'test','seed':101,'coverage':3.5,'length_mean':1000,'length_sd':200,
              'short_fraction':0.5,'short_length_mean':100,'short_length_sd':20,'plasmid_relative_depth':0.25}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ref=root/'reference.fasta'
            ref.write_text(''.join('>'+a+' circular=true\n'+s+'\n' for a,s in sequences.items()))
            provenance={'molecules':[{'accession':a,'type':'chromosome' if a=='CHR.1' else 'plasmid'} for a in sequences]}
            r=simulate_standard(ref,case,root/'reads.fastq',root/'simulation.json',provenance)
            totals={a:0 for a in sequences};short=0
            for header,sequence,quality in fastq_records(root/'reads.fastq'):
                accession=header.removeprefix('@').split(':')[0]
                fields=dict(x.split('=') for x in header.split()[1:]);start=int(fields['start']);length=int(fields['length'])
                self.assertLessEqual(length,len(sequences[accession]))
                expected=(sequences[accession]*2)[start:start+length]
                if fields['strand']=='-':expected=expected.translate(str.maketrans('ACGT','TGCA'))[::-1]
                self.assertEqual(sequence,expected);self.assertEqual(quality,'I'*length)
                totals[accession]+=length
                if fields['mode']=='short':short+=length
            self.assertEqual(totals,{'CHR.1':21000,'PL.1':74})
            self.assertEqual(short,sum(budget(n,0.5) for n in totals.values()))
            self.assertEqual(r['observed']['total_bases'],sum(totals.values()))
            again=simulate_standard(ref,case,root/'again.fastq',root/'again.json',provenance)
            self.assertEqual(r['reads_sha256'],again['reads_sha256'])

    def test_lower_depth_is_an_exact_baseline_sequence_prefix(self):
        case={'seed':202,'length_mean':100,'length_sd':20}
        sequence='ACGTTAC'*100
        full=list(sample_records(sequence,'CHR.1',case,30))
        low=list(sample_records(sequence,'CHR.1',case,10))
        self.assertEqual(''.join(r[2] for r in low),''.join(r[2] for r in full)[:7000])
        self.assertEqual(budget(1,2.5),3)
