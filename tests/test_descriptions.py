import unittest
from benchlib.descriptions import input_description

class DescriptionTests(unittest.TestCase):
    def test_source_attribution_survives_without_original_local_path(self):
        result=input_description({'dataset':{'id':'real','sample_id':'SAMPLE','source_kind':'real','files':{'reads':{'source':{'path':'/private/host/original.fastq'},'sha256':'a'*64}}},'reference':{'biosample':'SAMPLE','attribution':{'doi':'doi:example'},'url':'https://example.org/reference'}})
        self.assertEqual(result['dataset']['files']['reads']['source'],{'local_filename':'original.fastq'})
        self.assertEqual(result['reference']['attribution'],{'doi':'doi:example'})
        self.assertNotIn('/private/host',str(result))
