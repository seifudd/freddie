configfile: 'config.yaml'

def get_abs_path(path):
    import os
    abs_path = os.popen('readlink -f {}'.format(path)).read()
    return abs_path.rstrip("\r\n")
def make_slurm():
    import os
    os.makedirs('slurm'.format(outpath), mode=0o777, exist_ok=True)

outpath = get_abs_path(config['outpath'])
make_slurm()
config['exec']['freddie'] = get_abs_path(config['exec']['freddie'])

genes_d  = '{}/genes'.format(outpath)
mapped_d = '{}/mapped'.format(outpath)

gene_data=[
    'transcripts.tsv',
    'transcripts.fasta',
    'gene.fasta',
    'reads.fasta',
]
nanosim_read_analysis_files=[
    '_unaligned_length.pkl',
    '_aligned_region.pkl',
    '_aligned_reads.pkl',
    '_ht_length.pkl',
    '_match.hist',
    '_mis.hist',
    '_del.hist',
    '_ins.hist',
    '_first_match.hist',
    '_error_markov_model',
    '_ht_ratio.pkl',
    '.sam',
    '_match_markov_model',
    '_model_profile',
    '_error_rate.tsv',
]
nanosim_simulator_files=[
    '_reads.fasta',
    '.log',
]

rule all:
    input:
         expand('{}/{{gene}}/{{sample}}/{{out_file}}'.format(genes_d),          gene=config['genes'], sample=config['samples'], out_file=gene_data),
         expand('{}/{{gene}}/{{sample}}/simulated{{out_file}}'.format(genes_d), gene=config['genes'], sample=config['samples'], out_file=nanosim_simulator_files),
         expand('{}/{{gene}}/{{sample}}/simulated_reads.oriented.tsv'.format(genes_d),   gene=config['genes'], sample=config['samples']),
         expand('{}/{{gene}}/{{sample}}/simulated_reads.oriented.pdf'.format(genes_d),   gene=config['genes'], sample=config['samples']),

rule freddie_make:
    input:
        'Makefile'
    output:
        config['exec']['freddie']
    conda:
        'freddie.env'
    threads:
        6
    shell:
        'make -j {{threads}} -C {}'.format(config['exec']['freddie'][0:config['exec']['freddie'].rfind('/')])

rule nanosim_make:
    output:
        config['exec']['read_analysis'],
        config['exec']['simulator'],
        zipped   = temp(config['url']['nanosim'].split('/')[-1]),
        unzipped = temp(directory('NanoSim-{}/'.format(config['url']['nanosim'].split('/')[-1].split('.')[0]))),
    conda:
        'freddie.env'
    shell:
        '''
        wget {};
        unzip {{output.zipped}};
        cp {{output.unzipped}}/* extern/nanosim/ -r
        '''.format(config['url']['nanosim'])

rule minimap2_map:
    input:
        genome=config['references']['genome'],
        reads=lambda wildcards: config['samples'][wildcards.sample],
    output:
        temp('{}/{{sample}}.sam'.format(mapped_d))
    conda:
        'freddie.env'
    threads:
        32
    shell:
        'minimap2 -aY -x splice -t -eqx -t {threads} {input.genome} {input.reads} > {output}'

rule samtools_sort:
    input:
        '{}/{{sample}}.sam'.format(mapped_d),
    output:
        bam='{}/{{sample}}.sorted.bam'.format(mapped_d),
    conda:
        'freddie.env'
    threads:
        32
    shell:
        'samtools sort -T {}/{{wildcards.sample}}.tmp -m 2G -@ {{threads}} -O bam {{input}} > {{output.bam}}'.format(mapped_d)

rule samtools_index:
    input:
        bam='{}/{{sample}}.sorted.bam'.format(mapped_d),
    output:
        index='{}/{{sample}}.sorted.bam.bai'.format(mapped_d),
    conda:
        'freddie.env'
    threads:
        32
    shell:
        'samtools index -b -@ {threads} {input.bam}'

rule get_gene_data:
    input:
        reads  =  '{}/{{sample}}.sorted.bam'.format(mapped_d),
        index  =  '{}/{{sample}}.sorted.bam.bai'.format(mapped_d),
        gtf    =  config['annotations']['gtf'],
        genome =  config['references']['genome'],
        script =  config['exec']['gene_data'],
    params:
        out_dir=lambda wildcards: '{}/{}/{}'.format(genes_d, config['genes'][wildcards.gene], wildcards.sample)
    output:
        ['{}/{{gene}}/{{sample}}/{}'.format(genes_d, out_file) for out_file in gene_data]
    conda:
        'freddie.env'
    shell:
        '{input.script} -g {wildcards.gene} -t {input.gtf} -d {input.genome} -r {input.reads} -o {params.out_dir}'

rule nanosim_read_analysis:
    input:
        transcripts='{}/{{gene}}/{{sample}}/transcripts.fasta'.format(genes_d),
        reads='{}/{{gene}}/{{sample}}/reads.fasta'.format(genes_d),
        script =  config['exec']['read_analysis'],
    params:
        out_prefix='{}/{{gene}}/{{sample}}/training'.format(genes_d),
    output:
        ['{}/{{gene}}/{{sample}}/training{}'.format(genes_d, training_file) for  training_file in nanosim_read_analysis_files]
    conda:
        'freddie.env'
    threads:
        32
    shell:
        '{input.script} -i {input.reads} -r {input.transcripts} -t {threads} -o {params.out_prefix}'

rule nanosim_simulate:
    input:
        ['{}/{{gene}}/{{sample}}/training{}'.format(genes_d, training_file) for  training_file in nanosim_read_analysis_files],
        transcripts='{}/{{gene}}/{{sample}}/transcripts.fasta'.format(genes_d),
        script =  config['exec']['simulator'],
    params:
        in_prefix='{}/{{gene}}/{{sample}}/training'.format(genes_d),
        out_prefix='{}/{{gene}}/{{sample}}/simulated'.format(genes_d),
        read_count=10
    output:
        [genes_d+'/{gene}/{sample}/simulated'+simulation_file for  simulation_file in nanosim_simulator_files]
    conda:
        'freddie.env'
    shell:
        '{input.script} linear -r {input.transcripts} -c {params.in_prefix} -o {params.out_prefix} -n {params.read_count}'

rule get_nanosim_tsv:
    input:
        reads           = '{}/{{gene}}/{{sample}}/simulated_reads.fasta'.format(genes_d),
        transcripts_tsv = '{}/{{gene}}/{{sample}}/transcripts.tsv'.format(genes_d),
        script          = config['exec']['nanosim_tsv'],
    output:
        simulated_tsv='{}/{{gene}}/{{sample}}/simulated_reads.oriented.tsv'.format(genes_d),
        oriented_reads = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.fasta'.format(genes_d),
    conda:
        'freddie.env'
    shell:
        '{input.script} -nsr {input.reads} -t {input.transcripts_tsv} -or {output.oriented_reads} -ot {output.simulated_tsv}'

rule freddie_align:
    input:
        reads = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.fasta'.format(genes_d),
        gene = '{}/{{gene}}/{{sample}}/gene.fasta'.format(genes_d),
        script = config['exec']['freddie'],
    output:
        paf = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.paf'.format(genes_d),
    conda:
        'freddie.env'
    shell:
        '{input.script} align -g {input.gene} -r {input.reads} > {output.paf}'

rule freddie_plot:
    input:
        paf = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.paf'.format(genes_d),
        transcripts_tsv = '{}/{{gene}}/{{sample}}/transcripts.tsv'.format(genes_d),
        simulated_tsv='{}/{{gene}}/{{sample}}/simulated_reads.oriented.tsv'.format(genes_d),
        script = config['exec']['freddie'],
    output:
        dot = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.dot'.format(genes_d),
    conda:
        'freddie.env'
    shell:
        '{input.script} plot -p {input.paf} -a {input.transcripts_tsv} -s {input.simulated_tsv} > {output.dot}'

rule dot_to_pdf:
    input:
        dot = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.dot'.format(genes_d),
    output:
        pdf = '{}/{{gene}}/{{sample}}/simulated_reads.oriented.pdf'.format(genes_d),
    conda:
        'freddie.env'
    shell:
        'cat {input.dot} | dot -T pdf > {output.pdf}'
