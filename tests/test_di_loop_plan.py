from evergrowth.di.loop import DILoop


def make_loop(tmp_path):
    loop = DILoop.__new__(DILoop)
    loop.plan_path = tmp_path / "prompt_plan.md"
    return loop


def test_plan_file_contains_future_step_not_completed_response(tmp_path):
    loop = make_loop(tmp_path)
    response = (
        "Completed a careful review of the old classifier.\n"
        "Next plan: Draft a fresh reversible research question.\n"
        "next:25"
    )

    loop._write_plan(response)
    saved = loop.plan_path.read_text(encoding="utf-8")

    assert "Draft a fresh reversible research question." in saved
    assert "Completed a careful review" not in saved
    assert "next:25" not in saved


def test_missing_next_plan_uses_fresh_topic_fallback(tmp_path):
    loop = make_loop(tmp_path)

    loop._write_plan("Finished the task.\nnext:10")
    saved = loop.plan_path.read_text(encoding="utf-8")

    assert "Choose one fresh" in saved
    assert "Finished the task" not in saved
