"""Renders each brand's Creator Partnership Playbook as a PDF.

The numbers printed here are generated from the same parameters the acceptance simulator uses,
so the text and the labels cannot drift apart.
"""
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, Spacer

from common import BRANDS, BRAND_ORDER, path, read_csv
from pdfkit_util import make_doc, styles, table

ACCENT = {"northwind": "#0B2545", "vela": "#7A2E57", "kettle": "#8A4B08"}


def months(m):
    return "none" if m == 0 else f"{m} months"


def build(bid):
    b = BRANDS[bid]
    n, r = b["norms"], b["red"]
    st = styles(ACCENT[bid])
    out = path("brand", f"{bid}_partnership_playbook.pdf")
    doc, on_page = make_doc(out, f"{b['name']} Creator Partnership Playbook 2026",
                            f"{b['legal']} - Creator Partnership Playbook 2026 - fictional company for a synthetic dataset")
    s = []
    s.append(Paragraph(f"{b['name']}: Creator Partnership Playbook", st["title"]))
    s.append(Paragraph(f"{b['sector']} - {b['city']} - Edition 2026 - Internal guidance shared with agency partners", st["sub"]))
    s.append(Paragraph("1. About us", st["h"]))
    s.append(Paragraph(b["about"], st["body"]))

    s.append(Paragraph("2. Our standard terms", st["h"]))
    s.append(Paragraph("These are the terms we offer by default and the terms our legal team has pre-approved. "
                       "A package that matches this table is normally approved without escalation.", st["body"]))
    rows = [["Term", "Our standard"],
            ["Fee", "100% of the creator's published standard package rate."],
            ["Usage rights", f"{n['usage_months']} months from first publication on our owned channels and as paid partnership ads. "
                             "No whitelisting or dark posting without a separate fee. We do not take ownership of creator content."],
            ["Exclusivity", ("None. We do not ask creators to avoid other brands." if n["excl_months"] == 0 else
                             f"{n['excl_months']} months after the final deliverable, limited to direct competitors in {b['category_text']}.")],
            ["Payment", f"Net-{n['net_days']} from invoice."],
            ["Cancellation (kill) fee", f"{n['kill_pct']}% of the fee if we cancel after the kickoff date."],
            ["Revisions", f"{n['revisions']} rounds per deliverable at no extra charge."]]
    s.append(table(rows, [1.5 * inch, 5.2 * inch], accent=ACCENT[bid], st=st))

    s.append(Paragraph("3. Our limits", st["h"]))
    s.append(Paragraph("We are not able to approve a package that crosses any of the following lines. "
                       "These are hard limits, not opening positions.", st["body"]))
    lim = []
    if r["max_fee_mult"] is not None and r["max_fee_mult"] < 1.5:
        lim.append(f"Fee: we do not go above {round(r['max_fee_mult'] * 100)}% of the creator's standard package rate.")
    else:
        lim.append("Fee: we have room to pay above standard rate for the right package, up to 150% of the creator's standard package rate.")
    lim.append(f"Usage rights: we need at least {r['min_usage']} months of usage rights to run a campaign.")
    lim.append("Exclusivity: " + ("we do not require exclusivity." if r["min_excl"] == 0 else
                                  f"we require at least {r['min_excl']} months of category exclusivity."))
    lim.append(f"Payment: we cannot pay faster than net-{r['min_net']}.")
    lim.append(f"Kill fee: we do not agree to a cancellation fee above {r['max_kill']}% of the fee.")
    lim.append(f"Revisions: we need at least {r['min_rev']} " + ("round" if r["min_rev"] == 1 else "rounds") + " of revisions per deliverable.")
    for line in lim:
        s.append(Paragraph("&bull; " + line, st["body"]))

    s.append(Paragraph("4. How we weigh a package", st["h"]))
    s.append(Paragraph(
        f"Inside our limits we look at the package as a whole. In order of importance to us: {b['priority_order']}. "
        "A creator who gives us more on a term we care about (longer usage, longer exclusivity, a lower fee) "
        "makes it easier for us to say yes to something they care about on another term. "
        "Offers that move several terms against us at once are rarely approved, even when each single term is within our limits.",
        st["body"]))

    s.append(Paragraph("5. Recent approved deals", st["h"]))
    s.append(Paragraph("A sample of recent creator deals that we approved. Creator names are shortened.", st["body"]))
    deals = read_csv(path("brand", f"past_deals_{bid}.csv"))
    rows = [["Date", "Creator", "Fee (% of std)", "Usage", "Exclusivity", "Payment", "Kill fee", "Revisions"]]
    for d in deals:
        rows.append([d["date"], d["creator"], f"{d['fee_pct_of_standard']}%", d["usage"], d["exclusivity"],
                     d["payment"], f"{d['kill_fee_pct']}%", d["revisions"]])
    s.append(table(rows, [0.8 * inch, 0.9 * inch, 0.85 * inch, 0.85 * inch, 0.9 * inch, 0.7 * inch, 0.65 * inch, 0.9 * inch],
                   accent=ACCENT[bid], st=st))
    s.append(Spacer(1, 8))
    s.append(Paragraph("This playbook is guidance for negotiators. It is not a contract and does not create any obligation.", st["small"]))
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)
    return out


def main():
    for bid in BRAND_ORDER:
        print("wrote", build(bid))


if __name__ == "__main__":
    main()
