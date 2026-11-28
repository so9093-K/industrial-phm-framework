"""The link under an AI answer is the analysis screen the answer points to."""

from industrial_phm.runtime.operations_web_change_context import (
    analysis_descriptions,
    change_analyses,
    mentioned_analysis,
)


def test_an_answer_naming_one_screen_links_that_screen() -> None:
    offered = analysis_descriptions(
        change_analyses({"vibration_change": {}}, same_load=False), vibration=True
    )
    # 답이 말로 주파수 화면을 권하면, 정해 둔 후속 링크(기간 비교) 대신 그 화면이 링크가 된다.
    answer = "어느 대역에서 커졌는지 보려면 주파수 화면을 확인하세요."
    assert mentioned_analysis(answer, offered) == "open_spectrum"
    # 두 화면을 말하거나 아무 화면도 말하지 않으면 고르지 않는다.
    assert mentioned_analysis("기간 비교와 주파수 화면을 함께 보세요.", offered) is None
    assert mentioned_analysis("수평 진동이 초기의 10.1배입니다.", offered) is None


def test_the_same_current_comparison_is_run_not_pointed_to() -> None:
    offered = {
        "compare_same_load": "'같은 전류 범위 비교': 같은 전류 범위의 측정끼리 견준다.",
        "open_compare": "'기간 비교' 화면: 초기와 특이사항 구간을 견준다.",
    }
    assert mentioned_analysis("같은 전류 범위 비교를 해 보면 알 수 있습니다.", offered) is None
