#!/usr/bin/env python3
import argparse
from sys import stderr
from sklearn.cluster import DBSCAN
from sklearn.metrics.cluster import adjusted_rand_score
import numpy as np

def parse_args():
    parser = argparse.ArgumentParser(
        description="Cluster aligned reads into isoforms")
    parser.add_argument("-p",
                        "--paf",
                        type=str,
                        required=True,
                        help="Path to PAF file")
    parser.add_argument("-m",
                        "--min-samples",
                        type=str,
                        default=2,
                        help="sklearn DBSCAN min_samples param")
    parser.add_argument("-e",
                        "--eps",
                        type=str,
                        default=1,
                        help="sklearn DBSCAN eps param")
    parser.add_argument("-o",
                        "--output",
                        type=str,
                        required=True,
                        help="Put TSV file with results of clustering")
    args = parser.parse_args()
    return args

def compress_junctions(junctions):
    from statistics import mean
    result = list()
    MAX_JUMP = 10
    temp = [min(junctions)]
    for i in sorted(junctions)[1:]:
        if i - temp[-1] < MAX_JUMP:
            temp.append(i)
        else:
            result.append(round(mean(temp)))
            temp=[i]
    result.append(round(mean(temp)))
    return result

def read_paf(paf):
    reads = dict()
    is_first = True
    splice_junctions = list()
    for line in open(paf):
        line = line.rstrip().split('\t')
        if is_first:
            t_len = int(line[6])
            t_name = line[5]
            is_first = False
        if t_len != int(line[6]) or t_name != line[5]:
            print("Multiple targets detected in PAF file!", file=stderr)
            print(line, file=stderr)
            exit(-1)
        name = line[0]
        if not name in reads:
            reads[name] = [0 for _ in range(t_len)]
        if any('oc:c:1' in tag for tag in line[12:]):
            t_start = int(line[7])
            t_end = int(line[8])
            splice_junctions.append(t_start)
            splice_junctions.append(t_end)
            for i in range(t_start, t_end):
                reads[name][i] = 1
    names = sorted(list(reads.keys()))
    matrix = np.array([
        reads[name] for name in names
    ])
    cut_points = compress_junctions(splice_junctions)
    if cut_points[0] > 0:
        cut_points = [0] + cut_points
    if cut_points[-1] < t_len - 1:
        cut_points.append(t_len - 1)


    # print(len(reads))
    # print(matrix.shape)
    # std = np.std(matrix, axis=0)
    # print(len(std))
    # matrix = matrix[:, std != 0]
    print(matrix.shape)
    return names,matrix,cut_points

def get_ari_score(names, labels, true_labels):
    labels = [-(idx+1) if label < 0 else label for idx,label in enumerate(labels)]
    return adjusted_rand_score(true_labels, labels)

def get_pairwise_dist(matrix, labels, metric, out_file):
    from sklearn.metrics import pairwise_distances
    dist = pairwise_distances(matrix, metric=metric)
    np.set_printoptions(precision=2)
    print(metric, file=out_file)
    label_dict = {label:set() for label in labels}
    for rid,label in enumerate(labels):
        label_dict[label].add(rid)
    for label,rids in label_dict.items():
        intra_dist = list()
        inter_dist = list()
        for r1 in rids:
            for r2 in rids:
                if r1 >= r2:
                    continue
                intra_dist.append(dist[r1][r2])
            for r2 in range(len(labels)):
                if r2 in rids:
                    continue
                inter_dist.append(dist[r1][r2])
        out = [
            '{} ({})'.format(label, len(rids)),
            '{:.2f} (SD:{:.2f})'.format(np.mean(intra_dist), np.std(intra_dist)) if len(intra_dist) > 0 else 'NA (NA)',
            '{:.2f} (SD:{:.2f})'.format(np.mean(inter_dist), np.std(inter_dist)) if len(inter_dist) > 0 else 'NA (NA)',
        ]
        print('\t'.join((str(o) for o in out)), file=out_file)

def get_block_matrix(matrix, band_size):
    from math import ceil,floor
    height = matrix.shape[0]
    width = floor(matrix.shape[1] / band_size)
    remainder = matrix.shape[1] % band_size
    banded_matrix = np.zeros(shape=(height, width), dtype=float)
    for rid in range(height):
        end = 0
        for bid in range(width):
            start = end
            end = start + band_size + (remainder>0)
            remainder -= 1
            banded_matrix[rid][bid] = np.mean(a=matrix[rid][start:end])
    return banded_matrix

def get_banded_matrix(matrix, cut_points):
    height = matrix.shape[0]
    width = len(cut_points)-1
    banded_matrix = np.zeros(shape=(height, width), dtype=float)
    for rid in range(height):
        for bid in range(width):
            start = cut_points[bid]
            end = cut_points[bid+1]
            banded_matrix[rid][bid] = np.mean(a=matrix[rid][start:end])
    return banded_matrix

def plot_hierarchical_clustering(matrix, labels):
    from scipy.cluster import hierarchy
    import matplotlib.pyplot as plt

    print(matrix.shape, len(labels))
    Z = hierarchy.linkage(matrix, 'single')
    plt.figure()

    hierarchy.set_link_color_palette(['m', 'c', 'y', 'k'])
    fig, axes = plt.subplots(1, 1, figsize=(10, 5))
    # dn1 = hierarchy.dendrogram(Z, ax=axes[0], above_threshold_color='y',
    #                            orientation='top',
    #                            labels=labels)
    dn2 = hierarchy.dendrogram(Z, ax=axes,
                               above_threshold_color='#bcbddc',
                               orientation='right',
                               labels=labels)
    hierarchy.set_link_color_palette(None)  # reset to default after use
    plt.tight_layout()
    plt.savefig('out.pdf')

def main():
    args = parse_args()
    names,raw_matrix,cut_points = read_paf(paf=args.paf)
    print(cut_points)

    true_labels = {x.split('_')[0] for x in names}
    true_labels = {label:idx for idx,label in enumerate(true_labels)}
    true_labels = [true_labels[x.split('_')[0]] for x in names]
    print(len(true_labels), sorted(true_labels))

    block_matrix = get_block_matrix(matrix=raw_matrix, band_size=100)
    banded_matrix = get_banded_matrix(matrix=raw_matrix, cut_points=cut_points)

    # plot_hierarchical_clustering(matrix=banded_matrix, labels=['-'.join([str(y) for y in [true_labels[idx]]+x.split('_')[3:-1]]) for idx,x in enumerate(names)])
    plot_hierarchical_clustering(matrix=banded_matrix, labels=true_labels)
    out_file = open(args.output, 'w+')
    log_file = open(args.output+'.log', 'w+')

    for metric in ['jaccard', 'hamming', 'cityblock', 'cosine', 'euclidean', 'l1', 'l2', 'manhattan']:
        get_pairwise_dist(matrix=banded_matrix, labels=true_labels, metric=metric, out_file=log_file)
        for eps in list(np.arange(0.00001, 2, 0.01)) + list(np.arange(1, 100, 5)):
            for min_samples in range(2,3):
                clustering = DBSCAN(eps=eps, min_samples=min_samples, metric=metric).fit(banded_matrix)
                ari_score = get_ari_score(names=names, true_labels=true_labels, labels=list(clustering.labels_))
                if ari_score > 0:
                    print('{}\t{}\t{:7.4f}\t{:=7.4f}'.format(metric, min_samples, eps, ari_score), file=out_file)
                    for rid,label in enumerate(clustering.labels_):
                        print(banded_matrix.shape, file=out_file)
                        print('{}\t{}'.format(names[rid], label), file=out_file)
    out_file.close()
    log_file.close()

if __name__ == "__main__":
    main()
