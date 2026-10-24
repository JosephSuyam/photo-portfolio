from reel.build import make_environment

PAYLOAD = "<script>x</script>"
ESCAPED = "&lt;script&gt;x&lt;/script&gt;"


def test_album_template_untrusted_title_escaped() -> None:
    template = make_environment().get_template("album.html")
    html = template.render(
        site_title="Site",
        base_path="/",
        album={"title": PAYLOAD, "photos": []},
        next_album=None,
    )
    assert ESCAPED in html and PAYLOAD not in html


def test_index_template_untrusted_title_escaped() -> None:
    template = make_environment().get_template("index.html")
    html = template.render(
        site_title="Site",
        base_path="/",
        albums=[{"title": PAYLOAD, "slug": "x", "cover_url": "c.jpg"}],
    )
    assert ESCAPED in html and PAYLOAD not in html
