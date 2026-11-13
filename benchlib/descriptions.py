"""Portable declared input descriptions without local host paths."""
from pathlib import Path
import copy


def input_description(spec):
    dataset=spec['dataset'];reference=spec['reference']
    dataset_fields=('id','title','description','read_technology','source_kind','sample_id','reference_sample_id','run_accession','data_origin','published_identity','attribution')
    reference_fields=('id','accession','organism','biosample','sample_id','attribution','truth_scope','reference_confidence','download_sha256','canonical_fasta_sha256','member','archive_dependency','url')
    description={'dataset':{k:copy.deepcopy(dataset[k]) for k in dataset_fields if k in dataset},
                 'reference':{k:copy.deepcopy(reference[k]) for k in reference_fields if k in reference}}
    if reference.get('sources'):
        description['reference']['sources']=[{**{k:v for k,v in source.items() if k!='path'},**({'local_filename':Path(source['path']).name} if source.get('path') else {})} for source in reference['sources']]
    description['dataset']['files']={}
    for role,definition in dataset.get('files',{}).items():
        source=definition['source']
        location={'url':source['url']} if source.get('url') else {'local_filename':Path(source['path']).name}
        description['dataset']['files'][role]={'source':location,'sha256':definition.get('sha256')}
    return description
