from app.services.slack import format_slack_report


def test_headings_bold_lists_and_clickable_sources():
    report = (
        "## Summary\n\n**중요 내용** and __evidence__\n- [Source](https://example.com/a_b?q=1&x=2)"
    )
    assert format_slack_report(report) == (
        "*Summary*\n\n*중요 내용* and *evidence*\n• <https://example.com/a_b?q=1&amp;x=2|Source>"
    )


def test_mentions_are_escaped_but_generated_links_are_active():
    result = format_slack_report("<!channel> <@U123> & [source](https://example.com) @here")
    assert result == "&lt;!channel&gt; &lt;@U123&gt; &amp; <https://example.com|source> @here"


def test_bare_urls_code_and_parenthesized_link_targets():
    report = "https://example.com/a_b.\n`**literal**`\n[Source](https://example.com/a_(b))"
    assert format_slack_report(report) == (
        "<https://example.com/a_b>.\n`**literal**`\n<https://example.com/a_(b)|Source>"
    )


def test_fenced_code_keeps_markdown_literal():
    code = "```\n## literal heading\n**literal bold**\n- literal item\n```"
    assert format_slack_report(code) == code
