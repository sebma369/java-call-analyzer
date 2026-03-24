"""Call chain analysis functionality."""

from collections import deque


def build_call_chains(target_methods, callers, callees, max_depth=10):
    """Build upward and downward call chains for target methods."""
    up_chains = []
    down_chains = []

    for tm in target_methods:
        # 向上链（谁调用了我）
        if tm not in callers:
            up_chains.append((tm, ['(无调用者)']))
        else:
            # BFS 构造从根（调用者最远）到目标的链路
            queue = deque([[tm]])
            visited = set([tm])
            while queue:
                path = queue.popleft()
                current = path[-1]
                if current not in callers or not callers[current] or len(path) > max_depth:
                    up_chains.append((tm, list(reversed(path))))
                    continue
                for caller in callers[current]:
                    if caller in path:
                        # 避免循环
                        continue
                    queue.append(path + [caller])

        # 向下链（我调用了谁）
        if tm not in callees:
            down_chains.append((tm, ['(无被调用者)']))
        else:
            # BFS 构造从目标到叶子（被调用者最远）的链路
            queue = deque([[tm]])
            visited = set([tm])
            while queue:
                path = queue.popleft()
                current = path[-1]
                if current not in callees or not callees[current] or len(path) > max_depth:
                    down_chains.append((tm, path))
                    continue
                for callee in callees[current]:
                    if callee in path:
                        # 避免循环
                        continue
                    queue.append(path + [callee])

    return up_chains, down_chains