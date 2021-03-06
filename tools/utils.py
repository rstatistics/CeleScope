#!/bin/env python
#coding=utf8

import logging
import pandas as pd
import numpy as np
#from scipy.stats.kde import gaussian_kde
#from scipy.signal import argrelextrema
import subprocess
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def getlogger():
    logging.basicConfig(level = logging.INFO,format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger1 = logging.getLogger(__name__)
    logger2 = logging.getLogger(__name__)

    return logger1,logger2  

def format_number(number:int) -> str:
    return format(number,",")

def barcode_filter_with_magnitude(df, plot='magnitude.pdf', col='UMI', percent=0.1, expected_cell_num=3000):
    # col can be readcount or UMI
    # determine validated barcodes
    df = df.sort_values(col, ascending=False)
    idx = int(expected_cell_num*0.01) - 1
    idx = max(0, idx)

    # calculate read counts threshold
    threshold = int(df.iloc[idx, df.columns==col] * 0.1)
    threshold = max(1, threshold)
    validated_barcodes = df[df[col]>threshold].index

    fig = plt.figure()
    plt.plot(df[col])
    plt.hlines(threshold, 0, len(validated_barcodes), linestyle='dashed')
    plt.vlines(len(validated_barcodes), 0 , threshold, linestyle='dashed')
    plt.title('expected cell num: %s\n%s threshold: %s\ncell num: %s'%(expected_cell_num, col, threshold, len(validated_barcodes)))
    plt.loglog()
    plt.savefig(plot)

    return (validated_barcodes, threshold, len(validated_barcodes))

def barcode_filter_with_kde(df, plot='kde.pdf', col='UMI'):
    # col can be readcount or UMI
    # filter low values
    df = df.sort_values(col, ascending=False)
    arr = np.log10([i for i in df[col] if i/float(df[col][0]) > 0.001])

    # kde
    x_grid = np.linspace(min(arr), max(arr), 10000)
    density = gaussian_kde(arr, bw_method=0.1)
    y = density(x_grid)

    local_mins = argrelextrema(y, np.less)
    log_threshold = x_grid[local_mins[-1][0]]
    threshold = np.power(10,log_threshold)
    validated_barcodes = df[df[col]>threshold].index

    # plot
    fig, (ax1, ax2) = plt.subplots(2, figsize=(6.4,10))
    ax1.plot(x_grid, y)
    #ax1.axhline(y[local_mins[-1][0]], -0.5, log_threshold, linestyle='dashed')
    ax1.vlines(log_threshold, 0, y[local_mins[-1][0]], linestyle='dashed')
    ax1.set_ylim(0, 0.3)
    
    ax2.plot(df[col])
    ax2.hlines(threshold, 0, len(validated_barcodes), linestyle='dashed')
    ax2.vlines(len(validated_barcodes), 0 , threshold, linestyle='dashed')
    ax2.set_title('%s threshold: %s\ncell num: %s'%(col, int(threshold), len(validated_barcodes)))
    ax2.loglog()
    plt.savefig(plot)

    return (validated_barcodes, threshold, len(validated_barcodes))


def get_slope(x, y, window=200, step=10):
    assert len(x)==len(y)
    start=0
    last = len(x)
    res = [[],[]]
    while True:
        end = start + window 
        if end > last: break
        z = np.polyfit(x[start:end], y[start:end], 1)
        res[0].append(x[start])
        res[1].append(z[0])
        start += step
    return res

def barcode_filter_with_derivative(df, plot='derivative.pdf', col='UMI', window=500, step=5):
    # col can be readcount or UMI
    # filter low values
    df = df.sort_values(col, ascending=False)
    y = np.log10([i for i in df[col] if i/float(df[col][0]) > 0.001])
    x = np.log10(np.arange(len(y)) + 1)
    
    # derivative
    res = get_slope(x, y, window=window, step=step)
    res2 = get_slope(res[0], res[1], window=window, step=step) 
    g0 = [res2[0][i] for i,j in enumerate(res2[1]) if j>0] 
    cell_num = int(np.power(10,g0[0]))
    threshold = df[col][cell_num]
    validated_barcodes = df.index[0:cell_num]
    
    # plot
    fig, (ax1, ax2, ax3) = plt.subplots(3, figsize=(6.4,15))
    ax1.plot(res[0], res[1])
    
    ax2.plot(res2[0], res2[1])
    ax2.set_ylim(-1, 1)
    
    ax3.plot(df[col])
    ax3.hlines(threshold, 0, len(validated_barcodes), linestyle='dashed')
    ax3.vlines(len(validated_barcodes), 0 , threshold, linestyle='dashed')
    ax3.set_title('%s threshold: %s\ncell num: %s'%(col, int(threshold), len(validated_barcodes)))
    ax3.loglog()
    plt.savefig(plot)

    return (validated_barcodes, threshold, len(validated_barcodes))

def downsample(bam, barcodes, percent):
    """
    calculate median_geneNum and saturation based on a given percent of reads
    
    Args:
        bam - bam file 
        barcodes(set) - validated barcodes
        percent(float) - percent of reads in bam file.

    Returns:
        percent(float) - input percent
        median_geneNum(int) - median gene number
        saturation(float) - sequencing saturation
    
    Description:
        Sequencing Saturation = 1 - n_deduped_reads / n_reads.
        n_deduped_reads = Number of unique (valid cell-barcode, valid UMI, gene) combinations among confidently mapped reads. 
        n_reads = Total number of confidently mapped, valid cell-barcode, valid UMI reads.
    """
    logging.info ('working' + str(percent))
    cmd = ['samtools', 'view', '-s', str(percent), bam]
    p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    #nesting defaultdicts in an arbitrary depth
    def genDDict(dim=3):
        if dim==1:
            return defaultdict(int)
        else:
            return defaultdict(lambda: genDDict(dim-1))
    readDict =  genDDict()

    n_reads = 0
    while True:
        line = p1.stdout.readline()
        if not line.strip(): break
        tmp = line.strip().split()
        if tmp[-1].startswith('XT:Z:'):
            geneID = tmp[-1].replace('XT:Z:', '')
            cell_barcode, umi = tmp[0].split('_')[0:2]
            #filter invalid barcode
            if cell_barcode in barcodes: 
                n_reads += 1
                readDict[cell_barcode][umi][geneID] += 1
    p1.stdout.close()

    geneNum_list = []
    n_deduped_reads = 0
    for cell_barcode in readDict:
        genes = set()
        for umi in readDict[cell_barcode]:
            for geneID in readDict[cell_barcode][umi]:
                genes.add(geneID)
                if readDict[cell_barcode][umi][geneID] == 1:
                    n_deduped_reads += 1
        geneNum_list.append(len(genes))

    median_geneNum = np.median(geneNum_list) if geneNum_list else 0
    saturation = (1 - float(n_deduped_reads) / n_reads) * 100

    return "%.2f\t%.2f\t%.2f\n"%(percent, median_geneNum, saturation), saturation

if __name__ == '__main__':

    df = pd.read_table('SRR6954578_counts.txt', header=0)

    barcode_filter_with_magnitude(df)
    barcode_filter_with_kde(df)
    barcode_filter_with_derivative(df)


