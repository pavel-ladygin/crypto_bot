def min_cover_intervals(N, intervals):
    intervals.sort(key=lambda x: x[0])
    covered_end = 0
    idx = 0
    count = 0

    while covered_end < N:
        best_end = covered_end
        while idx < len(intervals) and intervals[idx][0] <= covered_end + 1:
            best_end = max(best_end, intervals[idx][1])
            idx += 1
        if best_end == covered_end:
            return "No"
        covered_end = best_end
        count += 1

    return "Yes\n" + str(count)


N, Q = map(int, input().split())
intervals = [tuple(map(int, input().split())) for _ in range(Q)]
print(min_cover_intervals(N, intervals))
