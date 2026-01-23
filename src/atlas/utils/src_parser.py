def traverse_tree(tree, finest_granularity=None):
    if finest_granularity is None:
        finest_granularity = []
    cursor = tree.walk()

    reached_root = False
    while not reached_root:
        yield cursor.node

        if cursor.goto_first_child() and cursor.node.type not in finest_granularity:
            continue

        if cursor.goto_next_sibling():
            continue

        retracing = True
        while retracing:
            if not cursor.goto_parent():
                retracing = False
                reached_root = True

            if cursor.goto_next_sibling():
                retracing = False
