from gfi.core import clean_url,dedupe,render,score

def test_clean_url_strips_tracking():
    assert clean_url("HTTPS://Example.com/a/?utm_source=x") == "https://example.com/a"
def test_dedupe_by_id():
    a={"id":"x","title":"a"}
    assert dedupe([a,a]) == [a]
def test_score_and_report():
    x={"id":"1","title":"Fed rate decision","url":"https://x","source":"Fed","category":"research","tier":"primary","published":"today","summary":"inflation"}
    assert score(x)>20
    assert "公开研究" in render([x],"2026-11-02")
