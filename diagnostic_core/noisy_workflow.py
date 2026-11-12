"""Freeze simulator assets and pair source fragments across error conditions."""
import argparse
import copy
import re
import shutil
from .common import ROOT, fingerprint, load, save, digest

def source_case(case):
    clean = copy.deepcopy(case)
    clean['simulation']['model'] = 'exact-lognormal-v1'
    clean.pop('error_profile', None)
    clean['id'] = case['source_case_id'] + '-fragments-seed-' + str(case['simulation']['seed'])
    clean['title'] = 'Frozen source fragments: ' + clean['id']
    clean['category'] = 'S1'
    clean['profile_id'] = 'matched-fragment-source-v1'
    clean['fingerprint'] = fingerprint({key: value for key, value in clean.items() if key != 'fingerprint'})
    return clean
