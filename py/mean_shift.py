#!/usr/bin/env python3
import argparse
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy import asarray as ar,exp
import numpy as np
from math import ceil,floor
from statistics import mean,stdev
from scipy.signal import find_peaks

def parse_args():
    parser = argparse.ArgumentParser(
        description="Cluster aligned reads into isoforms")
    parser.add_argument("-c",
                        "--raw-coverage",
                        type=str,
                        required=True,
                        help="Path to raw coverage TXT file")
    parser.add_argument("-p",
                        "--paf",
                        type=str,
                        required=True,
                        help="Path to PAF file of read alignments")
    parser.add_argument("-t",
                        "--tsv",
                        type=str,
                        required=True,
                        help="Path to TSV file")
    parser.add_argument("-bs",
                        "--histogram-bin-size",
                        type=float,
                        default=0.025,
                        help="Bin size for the histogram used for coverage curve fitting")
    parser.add_argument("-w",
                        "--window-size",
                        type=int,
                        default=1,
                        help="Non-overlapping window size")
    args = parser.parse_args()
    return args

# def thresholding_algo(y, lag, threshold, influence):
#     # from https://gist.github.com/ximeg/587011a65d05f067a29ce9c22894d1d2
#     signals = np.zeros(len(y))
#     filteredY = np.array(y)
#     avgFilter = [0]*len(y)
#     stdFilter = [0]*len(y)
#     avgFilter[lag - 1] = np.mean(y[0:lag])
#     stdFilter[lag - 1] = np.std(y[0:lag])
#     for i in range(lag, len(y) - 1):
#         if abs(y[i] - avgFilter[i-1]) > threshold * stdFilter [i-1]:
#             if y[i] > avgFilter[i-1]:
#                 signals[i] = 1
#             else:
#                 signals[i] = -1
#
#             filteredY[i] = influence * y[i] + (1 - influence) * filteredY[i-1]
#             avgFilter[i] = np.mean(filteredY[(i-lag):i])
#             stdFilter[i] = np.std(filteredY[(i-lag):i])
#         else:
#             signals[i] = 0
#             filteredY[i] = y[i]
#             avgFilter[i] = np.mean(filteredY[(i-lag):i])
#             stdFilter[i] = np.std(filteredY[(i-lag):i])
#
#     return dict(signals = np.asarray(signals),
#                 avgFilter = np.asarray(avgFilter),
#                 stdFilter = np.asarray(stdFilter))

def gaussian(x, a, x0, sigma):
    return a*exp(-(x-x0)**2/(2*sigma**2))

def ms_gradient(i, j, r_i, r_j, H_b, H_r,):
    e_b = gaussian(x=i, a=2, x0=j, sigma=H_b)
    e_r = gaussian(x=r_i, a=2, x0=r_j, sigma=H_r)
    return (j-i)*e_b*e_r

def get_neg_pos_breaks(l):
    result = list()
    for i in range(1, len(l)):
        if l[i] > 0 and not l[i-1] > 0:
            result.append(i)
    return result

def get_segments(coverage_l=0, ticks=set()):
    segs = list()
    segs.append((
        0,
        coverage_l,
    ))
    for i in range(coverage_l):
        if i in ticks:
            segs[-1] = (
                segs[-1][0],
                i,
            )
            segs.append((
                i,
                coverage_l,
            ))
    return segs

def get_variation(coverage, step):
    x = ar(list(np.arange(step/2, 1-step/2, step)))
    y = ar(
        np.histogram(
            [c for c in coverage if float(c) > 0.05],
            bins=np.arange(0,1,step)
        )[0]
    )
    popt,pcov = curve_fit(gaussian,x,y,maxfev=50000)
    return popt[2]**2

def get_hb_ticks(coverage, coverage_var, window_size, Hb_list, segmentations_count=3, lim=200):
    print("get_hb_ticks!")
    ticks = {x for x in range(window_size, len(coverage), window_size)}
    Hb_ticks = list()
    for H_b in Hb_list:
        segments = get_segments(len(coverage), ticks)
        for round_count in range(segmentations_count):
            gradients = list()
            for i,seg in enumerate(segments):
                i_pos = floor((seg[0]+seg[1])/2)
                i_rd = mean(coverage[seg[0]:seg[1]])
    #             print(i, seg, i_pos, i_rd)
                start = max(0,i-lim)
                end = min(i+lim, len(segments)-1)
                S = 0
                for j in range(start, end+1):
                    j_pos = floor((segments[j][0]+segments[j][1])/2)
                    j_rd = mean(coverage[segments[j][0]:segments[j][1]])
                    S += ms_gradient(i=i_pos, j=j_pos, r_i=i_rd, r_j=j_rd, H_b=H_b, H_r=coverage_var)
                gradients.append(S)
            new_segments = list()
            [(0,len(coverage))]

            ticks = {
                segments[seg_idx][0] for seg_idx in get_neg_pos_breaks(gradients)
            }
            segments = get_segments(len(coverage), ticks)
            print('Hb = {} Round = {} |ticks| = {}'.format(H_b, round_count, len(ticks)))
            print(ticks)
            Hb_ticks.append((
                ticks,
                'Hb = {}; Round = {}'.format(H_b, round_count)
            ))
    return Hb_ticks

def jaccard(a,b):
    i = len(a & b)
    j = len(a | b)
    if j == 0:
        return 0
    else:
        return i/j

def plot_coverage(coverage, transcripts, starts, ends, pos_to_rid, out_path):
    f, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(30,5*(3+1)), sharex=True)
    ax1.plot(range(len(coverage)), coverage)
    M = len(transcripts)
    h_step = 0.8/M
    for idx,(exons,introns) in enumerate(transcripts):
        h = 0.9 - idx*h_step
        for exon in exons:
            ax1.plot(exon, [h,h], color='black', marker='o', alpha=0.8)
        for intron in introns:
            ax1.plot(intron, [h,h], color='gray', alpha=0.2)
    neighborhood_size = 15
    x_jaccard = list()
    y_jaccard_r = list()
    y_jaccard_l = list()
    N = 0
    for rids in pos_to_rid:
        N = max(N, len(rids))
    plt.title('N = {}'.format(N))
    for i in range(len(pos_to_rid)):
        if len(pos_to_rid[i])/N < 0.01 or len(pos_to_rid[i]) < 3:
            x_jaccard.append(i)
            y_jaccard_r.append(0.0)
            y_jaccard_l.append(0.0)
            continue
        neighbors_r = set()
        prev = set()
        range_start = max(i-neighborhood_size, 0)
        range_end = i
        for j in range(range_start, range_end):
            prev = prev | pos_to_rid[j]
        y_jaccard_r.append(jaccard(prev, pos_to_rid[i]))

        neighbors_l = set()
        prev = set()
        range_start = i+1
        range_end = min(i+neighborhood_size+1, len(pos_to_rid))
        for j in range(range_start, range_end):
            prev = prev | pos_to_rid[j]
        y_jaccard_l.append(jaccard(prev, pos_to_rid[i]))
        x_jaccard.append(i)

    ax1.plot(x_jaccard, y_jaccard_r, color='r', alpha=0.25)
    ax1.plot(x_jaccard, y_jaccard_l, color='g', alpha=0.25)

    x_exonic_pos = list()
    y_exonic_jac_r = list()
    y_exonic_jac_l = list()

    cmap_r = plt.get_cmap('Reds')
    cmap_l = plt.get_cmap('Greens')
    for i in range(len(pos_to_rid)+1):
        if i == len(pos_to_rid) or len(pos_to_rid[i])/N < 0.01 or len(pos_to_rid[i]) < 3:
            if len(x_exonic_pos) >= 30:
                mu_r = mean(y_exonic_jac_r)
                sigma_r = stdev(y_exonic_jac_r)
                mu_l = mean(y_exonic_jac_l)
                sigma_l = stdev(y_exonic_jac_l)
                print(x_exonic_pos[0], x_exonic_pos[-1])
                stats_text = 'μ_r: {:.2f} σ_r: {:.2f} | μ_l: {:.2f} σ_l: {:.2f}'.format(mu_r, sigma_r, mu_l, sigma_l)
                print(stats_text)
                ax1.plot([x_exonic_pos[0],x_exonic_pos[-1]], [1.05,1.05], color='black', marker='x', alpha=1)
                text_x=x_exonic_pos[0]+(x_exonic_pos[-1]-x_exonic_pos[0])/10
                ax1.text(x=text_x, y=1.07, s=stats_text)

                norm_r = mpl.colors.Normalize(vmin=sigma_r, vmax=3*sigma_r)
                norm_l = mpl.colors.Normalize(vmin=sigma_l, vmax=3*sigma_l)

                for x,y_r,y_l in zip(x_exonic_pos,y_exonic_jac_r,y_exonic_jac_l):
                    if sigma_r > 0:
                        deviation_r = abs(mu_r-y_r)/sigma_r
                        if deviation_r > 0.5:
                            ax1.scatter(x=x,y=y_r, color=cmap_r(norm_r(deviation_r)), marker='>')
                    if sigma_l > 0:
                        deviation_l = abs(mu_l-y_l)/sigma_l
                        if deviation_l > 0.5:
                            ax1.scatter(x=x,y=y_l, color=cmap_l(norm_l(deviation_l)), marker='<')
                    # if deviation >= 0.5*sigma and deviation < 1.5*sigma:
                    #    plt.scatter(x=x,y=y, color='#ffeda0', marker='.')
                    # elif deviation >= 1.5*sigma and deviation < 2.5*sigma:
                    #     plt.scatter(x=x,y=y, color='#feb24c', marker='.')
                    # elif deviation >= 2.5*sigma:
                    #     plt.scatter(x=x,y=y, color='#f03b20', marker='.')
                x_exonic_pos = list()
                y_exonic_jac_r = list()
                y_exonic_jac_l = list()
            continue
        x_exonic_pos.append(i)
        y_exonic_jac_r.append(y_jaccard_r[i])
        y_exonic_jac_l.append(y_jaccard_l[i])

    # lag = neighborhood_size
    # threshold = 3
    # influence = 3
    y_rmv_r = list()
    y_add_r = list()
    for i,rids in enumerate(pos_to_rid):
        j_r = max(0, i-neighborhood_size)
        rids_rmved_r = len(pos_to_rid[j_r] - rids)
        rids_added_r = len(rids - pos_to_rid[j_r])
        y_rmv_r.append(rids_rmved_r)
        y_add_r.append(rids_added_r)
    ax2.plot(range(len(pos_to_rid)), y_rmv_r, color='#e41a1c', alpha=0.5)
    ax2.plot(range(len(pos_to_rid)), y_add_r, color='#377eb8', alpha=0.5)

    peaks_rmv, _ = find_peaks(y_rmv_r, height=max(N*0.01,3), distance=neighborhood_size*2)
    ax2.plot(peaks_rmv, [y_rmv_r[i] for i in peaks_rmv], "x", color='#e41a1c')
    peaks_add, _ = find_peaks(y_add_r, height=max(N*0.01,3), distance=neighborhood_size*2)
    ax2.plot(peaks_add, [y_add_r[i] for i in peaks_add], "x", color='#377eb8')

    plt.tight_layout()
    plt.savefig(out_path)

def plot_hb_ticks(coverage, Hb_ticks, out_path):
    subplot_count = len(Hb_ticks)
    f, ax = plt.subplots(subplot_count, 1, sharex=True, figsize=(30,5*subplot_count))
    for idx,(ticks,text) in enumerate(Hb_ticks):
        ax[idx].plot(range(len(coverage)), coverage)
        ax[idx].title.set_text(text)
        for tick in ticks:
            ax[idx].plot([tick,tick], [0,1], 'b', alpha=0.3)
    for tick in starts:
        ax[idx].scatter(x=tick,y=0.75, color='green', marker='^', alpha=0.2)
    for tick in ends:
        ax[idx].scatter(x=tick,y=0.25, color='red', marker='v', alpha=0.2)
    plt.tight_layout()
    plt.savefig(out_path)

def read_paf(paf):
    is_first = True
    starts = list()
    ends = list()
    pos_to_rid = list()
    read_name_to_id = dict()
    for line in open(paf):
        line = line.rstrip().split('\t')
        if is_first:
            t_len = int(line[6])
            t_name = line[5]
            is_first = False
            pos_to_rid = [set() for _ in range(t_len)]
        if t_len != int(line[6]) or t_name != line[5]:
            print("Multiple targets detected in PAF file!", file=stderr)
            print(line, file=stderr)
            exit(-1)
        name = line[0]
        if not name in read_name_to_id:
            read_name_to_id[name] = len(read_name_to_id)
        rid = read_name_to_id[name]
        if any('oc:c:1' in tag for tag in line[12:]):
            t_start = int(line[7])
            t_end = int(line[8])
            starts.append(t_start)
            ends.append(t_end)
            for i in range(t_start-1, t_end):
                pos_to_rid[i].add(rid)
    return pos_to_rid,starts,ends

def get_tsv_ticks(tsv):
    transcripts = list()
    starts = list()
    ends = list()
    for line in open(tsv):
        exons = list()
        introns = list()
        line = line.rstrip().split('\t')
        for interval in line[3].split(','):
            interval = interval.split('-')
            start = int(interval[0])
            end = int(interval[1])
            if len(exons) > 0:
                introns.append((exons[-1][1], start))
            exons.append((start,end))
        transcripts.append((exons,introns))
    return transcripts

def main():
    args = parse_args()

    transcripts = get_tsv_ticks(args.tsv)
    pos_to_rid,starts,ends = read_paf(args.paf)
    coverage = [float(c) for c in open(args.raw_coverage).readlines()]
    outpath = '{}.meanshift_coverage.pdf'.format(args.raw_coverage[0:args.raw_coverage.rfind('.')])
    plot_coverage(coverage=coverage, transcripts=transcripts, starts=starts, ends=ends, pos_to_rid=pos_to_rid, out_path=outpath)

    exit()
    coverage_var = get_variation(coverage=coverage, step=args.histogram_bin_size)

    Hb_list = [2,4,8]
    segmentations_count=3
    lim=200
    Hb_ticks = get_hb_ticks(coverage=coverage, coverage_var=coverage_var, window_size=args.window_size, Hb_list=Hb_list, segmentations_count=segmentations_count, lim=lim)

    outpath = '{}.meanshift_hb_ticks.pdf'.format(args.raw_coverage[0:args.raw_coverage.rfind('.')])
    plot_hb_ticks(coverage=coverage, Hb_ticks=Hb_ticks, out_path=outpath)

if __name__ == "__main__":
    main()
