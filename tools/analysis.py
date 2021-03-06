#!/bin/env python
#coding=utf8

import os
import sys
import json
import functools
import logging
from collections import defaultdict
from itertools import groupby
import glob,re

import numpy as np
import pandas as pd
from scipy.io import mmwrite
from scipy.sparse import csr_matrix
import pysam

FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level = logging.INFO, format = FORMAT)
toolsdir = os.path.realpath(sys.path[0] + '/../tools/')

def report_prepare(outdir,tsne_df,marker_df):
    json_file = outdir + '/../.data.json'
    if not os.path.exists(json_file):
        data = {}
    else:
        fh = open(json_file)
        data = json.load(fh)
        fh.close()

    data["cluster_tsne"] = cluster_tsne_list(tsne_df)
    data["gene_tsne"] = gene_tsne_list(tsne_df)
    data["marker_gene_table"] = marker_table(marker_df)

    with open(json_file, 'w') as fh:
        json.dump(data, fh)

def cluster_tsne_list(tsne_df):
    """
    tSNE_1	tSNE_2	cluster Gene_Counts
    return data list
    """
    tsne_df.cluster = tsne_df.cluster + 1
    res = []
    for cluster in sorted(tsne_df.cluster.unique()):
        sub_df = tsne_df[tsne_df.cluster==cluster]
        name = "cluster" + str(cluster)
        tSNE_1 = list(sub_df.tSNE_1)
        tSNE_2 = list(sub_df.tSNE_2)
        res.append({"name":name,"tSNE_1":tSNE_1,"tSNE_2":tSNE_2})
    return res

def gene_tsne_list(tsne_df):
    """
    return data dic
    """
    tSNE_1 = list(tsne_df.tSNE_1)
    tSNE_2 = list(tsne_df.tSNE_2)
    Gene_Counts = list(tsne_df.Gene_Counts)
    res = {"tSNE_1":tSNE_1,"tSNE_2":tSNE_2,"Gene_Counts":Gene_Counts}
    return res

def marker_table(marker_df):
    """
    return html code
    """
    marker_df = marker_df.loc[:,["cluster","gene","avg_logFC","pct.1","pct.2","p_val_adj"]]
    marker_df.cluster = marker_df.cluster.apply(lambda x:"cluster"+ str(x+1))
    marker_gene_table = marker_df.to_html(escape=False,index=False,table_id="marker_gene_table",justify="center")
    return marker_gene_table

def gene_convert(gtf_file,matrix_file):

    gene_id_pattern = re.compile(r'gene_id "(\S+)";')
    gene_name_pattern = re.compile(r'gene_name "(\S+)"')
    id_name = {}
    with open(gtf_file) as f:
        for line in f.readlines():
            if line.startswith('#!'):
                continue
            tabs = line.split('\t')
            gtf_type, attributes = tabs[2], tabs[-1]
            if gtf_type == 'gene':
                gene_id = gene_id_pattern.findall(attributes)[-1]
                gene_name = gene_name_pattern.findall(attributes)[-1]
                id_name[gene_id] = gene_name

    matrix = pd.read_csv(matrix_file,sep="\t")
    def convert(gene_id):
        if gene_id in id_name:
            return id_name[gene_id]
        else:
            return np.nan
    gene_name_col = matrix.geneID.apply(convert)
    matrix.geneID = gene_name_col
    matrix = matrix.rename({"geneID":"gene_name"}, axis='columns') 
    matrix = matrix.drop_duplicates(subset=["gene_name"],keep="first")
    matrix = matrix.dropna()
    return matrix    

def analysis(args):
    logging.info('analysis ...!')
    # check dir
    outdir = args.outdir
    sample = args.sample
    gtf_file = args.annot
    matrix_file = args.matrix_file
    if not os.path.exists(outdir):
        os.system('mkdir -p %s'%(outdir))
    
    # run
    logging.info("convert expression matrix.")
    new_matrix = gene_convert(gtf_file,matrix_file)  
    new_matrix_file = "{outdir}/{sample}_matrix.tsv".format(outdir=outdir,sample=sample)
    new_matrix.to_csv(new_matrix_file,sep="\t",index=False)
    logging.info("expression matrix written.")

    # run_R
    logging.info("Seurat running")
    cmd = "Rscript {app} --sample {sample} --outdir {outdir} --matrix_file {new_matrix_file}".format(
        app=toolsdir+"/run_analysis.R",sample = sample, outdir=outdir,new_matrix_file=new_matrix_file)
    os.system(cmd)
    logging.info("Seurat done.")

    # report
    tsne_df_file = "{outdir}/tsne_coord.tsv".format(outdir=outdir)
    marker_df_file = "{outdir}/markers.tsv".format(outdir=outdir)
    tsne_df = pd.read_csv(tsne_df_file,sep="\t")
    marker_df = pd.read_csv(marker_df_file,sep="\t")
    report_prepare(outdir,tsne_df,marker_df)

    logging.info('generate report ...!')
    from report import reporter
    t = reporter(name='analysis', outdir=args.outdir + '/..')
    t.get_report()
    logging.info('generate report done!')
    


def get_opts6(parser, sub_program):
    if sub_program:
        parser.add_argument('--outdir', help='output dir', required=True)
        parser.add_argument('--sample', help='sample name', required=True)
        parser.add_argument('--matrix_file', help='matrix file',required=True)
        parser.add_argument('--annot', help='gtf',required=True)


if __name__ == "__main__":
    tsne_df = pd.read_csv("/SGRNJ01/RD_dir/pipeline_test/zhouyiqi/scope_tools_1.0/out/06.analysis/tsne_coord.tsv",sep="\t")
    marker_df = pd.read_csv("/SGRNJ01/RD_dir/pipeline_test/zhouyiqi/scope_tools_1.0/out/06.analysis/markers.tsv",sep="\t")
    report_prepare("./out",tsne_df,marker_df)
    from report import reporter
    t = reporter(
        name='analysis',
        #stat_file=args.outdir + '/stat.txt',
        outdir= './out')
    t.get_report()
