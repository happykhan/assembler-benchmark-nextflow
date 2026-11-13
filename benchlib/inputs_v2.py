"""Scientific preparation from admitted dependencies; never download or install."""
from decimal import Decimal, ROUND_HALF_UP
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import struct
import subprocess
import tarfile
import uuid

from .catalogue import canonical_digest
from .io import digest, fastq_records, length_statistics
from .preparation import PreparationError, item_lock
from .references import canonical_fasta, read_fasta, sequence_statistics, source_records


def _save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def _safe(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',value):
        raise ValueError('Unsafe scientific cache identity')
    return value


def _budget(length, depth):
    return int((Decimal(length)*Decimal(str(depth))).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def _cached_dependency(item,cache):
    relative=Path(item['target']);path=cache/relative
    if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(cache):
        raise PreparationError('Missing or escaped admitted dependency: '+item['id'])
    observed=digest(path)
    if item.get('sha256'):
        if observed!=item['sha256']:raise PreparationError('Corrupt admitted dependency: '+item['id'])
    else:
        key=hashlib.sha256(str(relative).encode()).hexdigest()
        try:receipt=json.loads((cache/'.receipts'/(key+'.json')).read_text())
        except (OSError,ValueError) as error:raise PreparationError('Local dependency has no admission receipt') from error
        if receipt.get('sha256')!=observed:raise PreparationError('Local dependency differs from admission')
    if item.get('size_bytes') is not None and path.stat().st_size!=item['size_bytes']:
        raise PreparationError('Admitted dependency byte count differs')
    return path


def _reference_bytes(reference,dependencies,cache):
    if reference.get('archive_dependency'):
        item=next(d for d in dependencies if d['id']==reference['archive_dependency'])
        member=reference['member']
        with tarfile.open(_cached_dependency(item,cache),'r:gz') as stream:
            entry=stream.getmember(member['file'])
            if not entry.isfile() or entry.size!=member['bytes']:raise PreparationError('Reference member inventory differs')
            data=stream.extractfile(entry).read()
        if hashlib.sha256(data).hexdigest()!=member['sha256']:raise PreparationError('Reference member checksum differs')
        return data,'none'
    parts=[]
    for source in reference.get('sources') or [{'sha256':reference['download_sha256']}]:
        item=next(d for d in dependencies if d.get('sha256')==source['sha256'])
        parts.append(_cached_dependency(item,cache).read_bytes())
    data=b''.join(parts)
    if hashlib.sha256(data).hexdigest()!=reference['download_sha256']:raise PreparationError('Reference source checksum differs')
    return data,reference.get('compression','gzip')


def _verify_files(directory,receipt,cache):
    for name,checksum in receipt['file_sha256'].items():
        relative=Path(name);path=directory/relative
        if relative.is_absolute() or '..' in relative.parts or not path.is_file() or not path.resolve().is_relative_to(cache) or digest(path)!=checksum:
            raise PreparationError('Prepared cache bytes invalid: '+name)


def _prepare_reference(input_spec,dependencies,cache):
    reference=input_spec['reference']
    identity={k:reference[k] for k in ('canonical_fasta_sha256','download_sha256','quick_slice_bases','member') if k in reference}
    identity['molecules']=[{k:m[k] for k in ('accession','type','topology') if k in m} for m in reference.get('molecules',[])]
    key=canonical_digest(identity)
    directory=cache/'references'/'prepared'/key
    with item_lock(cache,'prepared-reference:'+key):
        if directory.exists():
            try:
                receipt=json.loads((directory/'receipt.json').read_text());_verify_files(directory,receipt,cache)
                return directory,json.loads((directory/'reference.json').read_text())
            except (OSError,ValueError,KeyError) as error:raise PreparationError('Invalid prepared reference cache') from error
        data,compression=_reference_bytes(reference,dependencies,cache);sequences=source_records(data,compression)
        if reference.get('quick_slice_bases'):
            if len(sequences)!=1:raise PreparationError('Validation fragment requires one source chromosome')
            original_accession,original=next(iter(sequences.items()));length=reference['quick_slice_bases']
            if not 0<length<=len(original):raise PreparationError('Reference fragment exceeds source')
            sequence=original[:length];sequences={reference['id']:sequence}
            molecules=[dict(accession=reference['id'],type='chromosome',topology='linear',source_accession=original_accession,source_interval_0based=[0,length],**sequence_statistics(sequence))]
        else:
            molecules=[]
            for declared in reference['molecules']:
                accession=declared['accession']
                if accession not in sequences:raise PreparationError('Declared reference molecule missing')
                stats=sequence_statistics(sequences[accession])
                for field in ('length_bp','sequence_sha256','gc_bases','ambiguous_bases'):
                    if field in declared and declared[field]!=stats[field]:raise PreparationError('Reference '+field+' differs')
                molecules.append(dict(declared,**stats))
            if set(sequences)!={m['accession'] for m in molecules}:raise PreparationError('Undeclared reference molecule')
        fasta=canonical_fasta(sequences,molecules)
        if reference.get('canonical_fasta_sha256') and not reference.get('archive_dependency') and hashlib.sha256(fasta).hexdigest()!=reference['canonical_fasta_sha256']:
            raise PreparationError('Canonical reference checksum differs')
        metadata={'schema_version':2,'id':reference['id'],'organism':reference.get('organism'),'accession':reference.get('accession'),
            'reference_sha256':hashlib.sha256(fasta).hexdigest(),'molecules':molecules,
            'truth_scope':reference.get('truth_scope',reference.get('reference_confidence','Published reference comparator; agreement with real reads is not independently validated truth.'))}
        directory.parent.mkdir(parents=True,exist_ok=True);temporary=directory.with_name('.'+key+'.partial-'+uuid.uuid4().hex);temporary.mkdir()
        try:
            (temporary/'reference.fasta').write_bytes(fasta);_save(temporary/'reference.json',metadata)
            for i,molecule in enumerate(molecules):
                a=molecule['accession'];(temporary/('molecule-'+str(i)+'.fasta')).write_text('>'+a+'\n'+sequences[a]+'\n')
            _save(temporary/'receipt.json',{'file_sha256':{p.name:digest(p) for p in temporary.iterdir()}})
            os.rename(temporary,directory)
        finally:
            if temporary.exists():shutil.rmtree(temporary)
    return directory,metadata


def _pair_id(header):
    name=header.removeprefix('@').split()[0]
    return name[:-2] if name.endswith(('/1','/2')) else name


def _fastq_statistics(files,paired=False):
    lengths=[];pairs=0
    if paired:
        for first,second in itertools.zip_longest(fastq_records(files[0]),fastq_records(files[1])):
            if first is None or second is None or _pair_id(first[0])!=_pair_id(second[0]):raise ValueError('Paired FASTQ identifiers/counts differ')
            for record in (first,second):
                if not set(record[1].upper())<=set('ACGTRYSWKMBDHVN') or any(not 33<=ord(q)<=126 for q in record[2]):
                    raise ValueError('Invalid FASTQ bases or quality characters')
            pairs+=1;lengths.extend([len(first[1]),len(second[1])])
    else:
        for header,sequence,quality in fastq_records(files[0]):
            if not set(sequence.upper())<=set('ACGTRYSWKMBDHVN') or any(not 33<=ord(q)<=126 for q in quality):
                raise ValueError('Invalid FASTQ bases or quality characters')
            lengths.append(len(sequence))
    result=length_statistics(lengths)
    if paired:result['pair_count']=pairs
    return result


def _native_reads(directory,reference,recipe):
    sequences=read_fasta((directory/'reference.fasta').read_text())
    files,replicons,all_lengths,modes=[],[],[],{}
    for i,molecule in enumerate(reference['molecules']):
        accession=molecule['accession'];sequence=sequences[accession];size=len(sequence);doubled=sequence+sequence
        if not set(sequence)<=set('ACGT'):raise ValueError('Native sampler requires unambiguous reference sequence')
        depth=recipe['coverage']*(recipe.get('plasmid_relative_depth',1) if molecule['type']=='plasmid' else 1)
        target=_budget(size,depth);short=_budget(target,recipe.get('short_fraction',0));lengths=[];trimmed=0
        path=directory/('.native-'+str(i)+'.fastq')
        with path.open('w') as stream:
            mode_recipes=[('short',short,recipe.get('short_length_mean',1000),recipe.get('short_length_sd',250)),
                          ('long',target-short,recipe['length_mean'],recipe['length_sd'])]
            for label,bases,mean,sd in mode_recipes:
                if mean<=0 or sd<0:raise ValueError('Invalid native fragment length parameters')
                rng=random.Random('native-error-free-v2:%s:%s:%s'%(recipe['seed'],accession,label));emitted,index=0,0
                while emitted<bases:
                    sampled=max(1,round(rng.gammavariate((mean/sd)**2,sd**2/mean))) if sd else max(1,round(mean))
                    length=min(sampled,size,bases-emitted)
                    start=rng.randrange(size) if molecule['topology']=='circular' else rng.randrange(size-length+1)
                    strand='-' if rng.getrandbits(1) else '+'
                    fragment=doubled[start:start+length] if molecule['topology']=='circular' else sequence[start:start+length]
                    if strand=='-':fragment=fragment.translate(str.maketrans('ACGT','TGCA'))[::-1]
                    stream.write('@%s:%s:%s start=%s length=%s strand=%s mode=%s\n%s\n+\n%s\n'%(accession,label,index,start,length,strand,label,fragment,'I'*length))
                    lengths.append(length);emitted+=length;index+=1;trimmed+=sampled>length
                    mode=modes.setdefault(label,{'read_count':0,'total_bases':0});mode['read_count']+=1;mode['total_bases']+=length
        files.append((path,len(lengths)));all_lengths.extend(lengths)
        replicons.append(dict(accession=accession,topology=molecule['topology'],target_bases=target,
            observed_bases=sum(lengths),realised_coverage=sum(lengths)/size,native_length_or_budget_trim_count=trimmed,
            **length_statistics(lengths)))
    rng=random.Random('native-error-free-v2:%s:interleave'%recipe['seed'])
    streams=[p.open() for p,_ in files];remaining=[n for _,n in files]
    try:
        with (directory/'reads.fastq').open('w') as out:
            while sum(remaining):
                choice=rng.randrange(sum(remaining));index=0
                while choice>=remaining[index]:choice-=remaining[index];index+=1
                out.write(''.join(next(streams[index]) for _ in range(4)));remaining[index]-=1
    finally:
        for stream in streams:stream.close()
        for path,_ in files:path.unlink()
    observed=length_statistics(all_lengths);short=modes.get('short',{'read_count':0,'total_bases':0})
    observed.update(per_replicon=replicons,short_mode_base_fraction=short['total_bases']/observed['total_bases'],
                    short_mode_read_fraction=short['read_count']/observed['read_count'],modes=modes)
    return ['reads.fastq'],observed,[],{'native-error-free-v2':'2'}


def _art_reads(directory,reference,recipe):
    if recipe.get('version')!='2016.06.05' or recipe.get('profile')!='HS25':
        raise ValueError('The verified ART recipe pins 2016.06.05 and HS25')
    if recipe.get('errors','builtin_profile')!='builtin_profile':
        raise ValueError('ART error settings must use the declared built-in profile and rates')
    version=subprocess.run(['art_illumina','--version'],capture_output=True,text=True)
    text=(version.stdout+version.stderr).strip()
    if '2.5.8' not in text:raise ValueError('Pinned ART binary Q version 2.5.8 is required')
    if recipe.get('coverage_convention')!='total_read_bases_per_reference_base' or recipe.get('boundary_policy')!='linear_no_wrap':
        raise ValueError('Unsupported ART coverage or boundary convention')
    commands=[];replicons=[]
    with (directory/'reads_1.fastq').open('w') as mate1,(directory/'reads_2.fastq').open('w') as mate2:
        for i,molecule in enumerate(reference['molecules']):
            prefix='art-'+str(i)+'-';ref='molecule-'+str(i)+'.fasta'
            seed=int(canonical_digest([recipe['seed'],molecule['accession']])[:8],16)%2147483646+1
            depth=recipe['coverage']*(recipe.get('plasmid_relative_depth',1) if molecule['type']=='plasmid' else 1)
            command=['art_illumina','-ss',recipe['profile'],'-i',ref,'-p','-l',str(recipe['read_length']),
                '-f',str(depth),'-m',str(recipe['fragment_mean']),'-s',str(recipe['fragment_sd']),'-rs',str(seed),
                '-ir',str(recipe.get('insertion_rate_r1',0.00009)),'-ir2',str(recipe.get('insertion_rate_r2',0.00015)),
                '-dr',str(recipe.get('deletion_rate_r1',0.00011)),'-dr2',str(recipe.get('deletion_rate_r2',0.00023)),
                '-qs',str(recipe.get('quality_shift_r1',0)),'-qs2',str(recipe.get('quality_shift_r2',0)),
                '-nf',str(recipe.get('mask_n',1)),'-k',str(recipe.get('max_indel',recipe['read_length'])),'-na','-o',prefix]
            with (directory/(prefix+'log')).open('w') as log:
                subprocess.run(command,cwd=directory,stdout=log,stderr=subprocess.STDOUT,check=True)
            first=directory/(prefix+'1.fq');second=directory/(prefix+'2.fq');stats=_fastq_statistics([first,second],paired=True)
            if stats['total_bases']<=0:raise ValueError('ART produced no reads for a native molecule')
            if stats['min_length']!=recipe['read_length'] or stats['max_length']!=recipe['read_length']:
                raise ValueError('ART output read length differs from its recipe')
            expected=depth*molecule['length_bp']
            # ART rounds the requested fragment count; do not pretend it emits
            # exact base budgets. A gross per-mate/total-depth error must fail.
            tolerance=max(expected*.02,4*recipe['read_length'])
            if abs(stats['total_bases']-expected)>tolerance:
                raise ValueError('ART realised total coverage differs from its recipe')
            for left,right in zip(fastq_records(first),fastq_records(second)):
                key=molecule['accession']+':'+_pair_id(left[0])
                for stream,record,n in [(mate1,left,1),(mate2,right,2)]:
                    stream.write('@'+key+'/'+str(n)+'\n'+record[1]+'\n+\n'+record[2]+'\n')
            commands.append({'molecule':molecule['accession'],'argv':command,'sampling_seed':seed,
                             'coverage_convention':'total_read_bases_per_reference_base'})
            replicons.append(dict(accession=molecule['accession'],target_coverage=depth,
                realised_coverage=stats['total_bases']/molecule['length_bp'],boundary_policy='linear_no_wrap',**stats))
            for suffix in ['1.fq','2.fq','1.aln','2.aln']:(directory/(prefix+suffix)).unlink(missing_ok=True)
    observed=_fastq_statistics([directory/'reads_1.fastq',directory/'reads_2.fastq'],paired=True);observed['per_replicon']=replicons
    return ['reads_1.fastq','reads_2.fastq'],observed,commands,{'art_package':'2016.06.05','art_binary':'2.5.8'}


def _external_reads(directory,input_spec,dependencies,cache):
    dataset=input_spec['dataset'];published=input_spec['recipe']['method']=='published-frozen-reads-v1'
    roles={'reads':{}} if published else dataset['files'];output=[]
    for role,file in roles.items():
        if published:item=next(d for d in dependencies if d['kind']=='published_reads')
        else:
            candidates=[d for d in dependencies if d['kind']=='real_reads' and d.get('source')==file['source']]
            if len(candidates)!=1:raise PreparationError('Real read role does not resolve to one admitted dependency')
            item=candidates[0]
        source=_cached_dependency(item,cache)
        name={'reads':'reads.fastq','r1':'reads_1.fastq','r2':'reads_2.fastq'}[role]
        with (gzip.open(source,'rb') if item.get('compression')=='gzip' else source.open('rb')) as incoming,(directory/name).open('wb') as outgoing:
            shutil.copyfileobj(incoming,outgoing,1024*1024)
        output.append(name)
    output.sort();observed=_fastq_statistics([directory/n for n in output],paired=input_spec['layout']=='short_paired')
    if published:
        identity=dataset['published_identity']
        if digest(directory/'reads.fastq')!=identity['uncompressed_reads_sha256']:
            raise PreparationError('Published decompressed read checksum differs')
    else:
        if not dataset.get('sample_id') or dataset['sample_id']!=dataset.get('reference_sample_id'):
            raise PreparationError('Real read/reference sample identity differs')
        observed.update(sample_id=dataset['sample_id'],run_accession=dataset.get('run_accession'))
    return output,observed,[],{}


def _reorder_reads(directory,files,order):
    """Bounded-memory record permutation; duplicate records remain separate."""
    if not isinstance(order,dict) or order.get('method') not in ('hash','length_ascending'):
        raise ValueError('Read order requires method hash or length_ascending')
    seed=order.get('seed',0)
    if type(seed) is not int or seed<0:raise ValueError('Read-order seed must be nonnegative')
    database=directory/'.read-order.sqlite';connection=sqlite3.connect(database)
    connection.execute('CREATE TABLE records (idx INTEGER PRIMARY KEY, sortkey TEXT, offsets TEXT, lengths TEXT, sha TEXT)')
    sources=[(directory/name).open('rb') for name in files];source_order=hashlib.sha256();count=0
    try:
        while True:
            offsets=[f.tell() for f in sources];parts=[];lengths=[];sequence_bases=0
            for stream in sources:
                header=stream.readline()
                if not header:parts.append(None);lengths.append(0);continue
                sequence,plus,quality=[stream.readline() for _ in range(3)]
                if not header.startswith(b'@') or not plus.startswith(b'+') or not all(x.endswith(b'\n') for x in (header,sequence,plus,quality)):
                    raise ValueError('Read-order transform requires complete four-line records')
                raw=header+sequence+plus+quality;parts.append(raw);lengths.append(len(raw));sequence_bases+=len(sequence.rstrip(b'\r\n'))
            if all(p is None for p in parts):break
            if any(p is None for p in parts):raise ValueError('Mates end at different record positions')
            sha=hashlib.sha256(b''.join(parts)).hexdigest();source_order.update(bytes.fromhex(sha))
            key=hashlib.sha256(('read-order-v2:'+str(seed)+':').encode()+struct.pack('>Q',count)).hexdigest() if order['method']=='hash' else '%020d'%sequence_bases
            connection.execute('INSERT INTO records VALUES (?,?,?,?,?)',(count,key,json.dumps(offsets),json.dumps(lengths),sha));count+=1
        connection.commit();multiset=hashlib.sha256()
        for sha, in connection.execute('SELECT sha FROM records ORDER BY sha,idx'):multiset.update(bytes.fromhex(sha))
        outputs=[(directory/('.ordered-'+name)).open('wb') for name in files];ordered=hashlib.sha256();written=0
        try:
            for offsets,lengths,sha in connection.execute('SELECT offsets,lengths,sha FROM records ORDER BY sortkey,idx'):
                chunks=[]
                for source,offset,length in zip(sources,json.loads(offsets),json.loads(lengths)):
                    source.seek(offset);chunks.append(source.read(length))
                if hashlib.sha256(b''.join(chunks)).hexdigest()!=sha:raise ValueError('Read bytes changed during permutation')
                for output,chunk in zip(outputs,chunks):output.write(chunk)
                ordered.update(bytes.fromhex(sha));written+=1
        finally:
            for f in outputs:f.close()
        if written!=count:raise ValueError('Read-order permutation lost records')
    finally:
        for f in sources:f.close()
        connection.close();database.unlink(missing_ok=True)
    for name in files:os.replace(directory/('.ordered-'+name),directory/name)
    return {'method':order['method'],'seed':seed,'record_count':count,'unit':'mate_pair' if len(files)==2 else 'read',
            'record_multiset_sha256':multiset.hexdigest(),'source_order_sha256':source_order.hexdigest(),'output_order_sha256':ordered.hexdigest()}


def _verify_input(directory,input_spec,cache):
    if digest(directory/'input.json')!=(directory/'input.sha256').read_text().strip():
        raise PreparationError('Prepared input metadata checksum differs')
    receipt=json.loads((directory/'input.json').read_text())
    for field in ('id','dataset_id','science_key','read_technology','source_kind','layout','recipe'):
        if receipt.get(field)!=input_spec.get(field):raise PreparationError('Prepared input contract differs: '+field)
    _verify_files(directory,receipt,cache)
    return receipt


def prepare_input(input_spec,plan,cache,output):
    """Prepare/reuse one recipe; dependency admission must already have passed."""
    method=input_spec['recipe']['method']
    if method in ('native-error-free-v2','art-illumina-v1','published-frozen-reads-v1') and input_spec['source_kind']!='simulated':
        raise ValueError('Simulated inputs cannot be labelled real')
    if method=='art-illumina-v1' and input_spec['layout']!='short_paired' or method=='native-error-free-v2' and input_spec['layout']!='long_single':
        raise ValueError('Input method and read layout differ')
    cache=Path(cache).resolve();output=Path(output).absolute()
    directory=cache/'inputs'/_safe(input_spec['dataset_id'])/_safe(input_spec['id'])
    with item_lock(cache,'scientific-input:'+input_spec['id']):
        if directory.exists():receipt=_verify_input(directory,input_spec,cache)
        else:
            # Nextflow passes only this input's admitted file dependencies;
            # software/image dependencies were handled on the submission host.
            dependencies=[item for item in plan['dependencies'] if item['id'] in input_spec['dependencies']
                          and item['kind'] not in ('software','software_environment','container_image')]
            reference_dir,reference=_prepare_reference(input_spec,dependencies,cache)
            directory.parent.mkdir(parents=True,exist_ok=True)
            temporary=directory.with_name('.'+directory.name+'.partial-'+uuid.uuid4().hex);temporary.mkdir()
            try:
                for source in reference_dir.iterdir():
                    if source.name=='receipt.json':continue
                    (temporary/source.name).symlink_to(os.path.relpath(source,temporary))
                method=input_spec['recipe']['method']
                if method=='native-error-free-v2':
                    files,observed,commands,versions=_native_reads(temporary,reference,input_spec['recipe'])
                elif method=='art-illumina-v1':files,observed,commands,versions=_art_reads(temporary,reference,input_spec['recipe'])
                elif method in ('local-files-v1','downloaded-files-v1','published-frozen-reads-v1'):
                    files,observed,commands,versions=_external_reads(temporary,input_spec,dependencies,cache)
                else:raise ValueError('Unsupported scientific input method: '+method)
                if input_spec['recipe'].get('read_order'):
                    observed['read_order']=_reorder_reads(temporary,files,input_spec['recipe']['read_order'])
                receipt={key:input_spec[key] for key in ('id','dataset_id','science_key','read_technology','source_kind','layout','recipe')}
                receipt.update(schema_version=2,status='completed',files=files,reference='reference.fasta',
                    reference_metadata='reference.json',observed=observed,commands=commands,software_versions=versions,
                    file_sha256={p.name:digest(p) for p in temporary.iterdir() if p.is_file()})
                _save(temporary/'input.json',receipt)
                (temporary/'input.sha256').write_text(digest(temporary/'input.json')+'\n')
                _verify_input(temporary,input_spec,cache);os.rename(temporary,directory)
            finally:
                if temporary.exists():shutil.rmtree(temporary)
    if output.exists() or output.is_symlink():
        if not output.is_symlink() or output.resolve()!=directory:raise FileExistsError('Task input destination already exists')
    else:
        output.parent.mkdir(parents=True,exist_ok=True);output.symlink_to(directory,target_is_directory=True)
    return receipt
