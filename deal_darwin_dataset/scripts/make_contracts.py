"""Builds four fictional creator-brand contracts, their answer keys, a messy scan, and ground-truth counters.

A  fair contract (Northwind x Maya Okafor)                        - tests false positives
B  predatory contract (Vela Beauty x Priya Nair)                  - eight planted traps
C  buried / ambiguous contract (Kettle & Co x Jordan Lee)         - traps hidden in definitions and a schedule
D  messy scan (Northwind x Diego Ramirez)                         - handwritten overrides, coffee stain, skew, noise
"""
import html
import os
import random
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from common import (BRANDS, CREATORS, PERSONAS, GRID, OFFER_KEYS, SEED, brand_eval, creator_utility,
                    iter_grid, offer_text, path, write_csv, write_json, USAGE_PERPETUAL, REV_UNLIMITED)
from pdfkit_util import make_doc, styles, table, FONT_DIR

FIELDS = ["fee", "usage_rights", "exclusivity", "payment_terms", "kill_fee", "revisions",
          "termination", "content_approval"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def norm(s):
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", s).strip().lower()


class Contract:
    def __init__(self, cid, title, brand, creator, persona, scenario, filename):
        self.cid, self.title, self.brand, self.creator = cid, title, brand, creator
        self.persona, self.scenario, self.filename = persona, scenario, filename
        self.blocks, self.keys, self.extras, self.distractors = [], {}, {}, []
        self.as_written = {}

    def k(self, field, sentence, **meta):
        self.keys[field] = dict(quote=sentence, **meta)
        return sentence

    def nf(self, field, **meta):
        self.keys[field] = dict(quote=None, status="not_found", page=None, **meta)

    def extra(self, name, sentence, **meta):
        self.extras[name] = dict(quote=sentence, **meta)
        return sentence

    def sec(self, num, head, *parts):
        self.blocks.append(("sec", num, head, " ".join(parts)))

    def h(self, text):
        self.blocks.append(("h", text))

    def p(self, text):
        self.blocks.append(("p", text))

    def pagebreak(self):
        self.blocks.append(("pb",))

    def tbl(self, data, widths):
        self.blocks.append(("tbl", data, widths))


def parties_block(c, brand_id, creator_id, effective):
    b, cr = BRANDS[brand_id], CREATORS[creator_id]
    c.p(f"This Creator Partnership Agreement (the “Agreement”) is entered into as of {effective} "
        f"(the “Effective Date”) between {b['legal']}, {BRAND_ADDR[brand_id]} (“Brand”), and "
        f"{cr['name']}, an individual residing at {cr['address']}, operating the {cr['platform']} account "
        f"{cr['handle']} (“Creator”).")


BRAND_ADDR = {"northwind": "1200 Alder Street, Portland, OR 97209",
              "vela": "800 Wilshire Boulevard, Los Angeles, CA 90017",
              "kettle": "500 Barton Springs Road, Austin, TX 78704"}


def signature(c, brand_id, creator_id):
    b, cr = BRANDS[brand_id], CREATORS[creator_id]
    st = styles("#222222", serif=True)
    left = (f"<b>BRAND</b><br/>{esc(b['legal'])}<br/><br/>By: ______________________<br/>"
            f"Name: {esc(SIGNER[brand_id])}<br/>Title: {esc(SIGNER_TITLE[brand_id])}<br/>Date: ______________")
    right = (f"<b>CREATOR</b><br/>{esc(cr['name'])}<br/><br/>Signature: __________________<br/>"
             f"Name: {esc(cr['name'])}<br/><br/>Date: ______________")
    c.blocks.append(("sig", left, right))


SIGNER = {"northwind": "Marcus Hale", "vela": "Dana Whitfield", "kettle": "Theo Brandt"}
SIGNER_TITLE = {"northwind": "Director of Partnerships", "vela": "VP, Influencer Marketing", "kettle": "Head of Growth"}


def render_pdf(c, out):
    st = styles("#222222", serif=True)
    doc, on_page = make_doc(out, c.title, f"{c.title} - fictional agreement for a synthetic dataset")
    s = [Paragraph(esc(c.title), st["title"]), Spacer(1, 6)]
    for blk in c.blocks:
        kind = blk[0]
        if kind == "h":
            s.append(Paragraph(esc(blk[1]), st["h"]))
        elif kind == "p":
            s.append(Paragraph(esc(blk[1]), st["clause"]))
        elif kind == "sec":
            s.append(Paragraph(f"<b>{blk[1]}. {esc(blk[2])}.</b> {esc(blk[3])}", st["clause"]))
        elif kind == "pb":
            s.append(PageBreak())
        elif kind == "tbl":
            s.append(table(blk[1], blk[2], accent="#222222", st=st))
            s.append(Spacer(1, 8))
        elif kind == "sig":
            t = Table([[Paragraph(blk[1], st["cell"]), Paragraph(blk[2], st["cell"])]],
                      colWidths=[3.3 * inch, 3.3 * inch])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 14)]))
            s.append(Spacer(1, 10))
            s.append(t)
    doc.build(s, onFirstPage=on_page, onLaterPages=on_page)


def page_texts(pdf):
    info = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout
    n = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    out = []
    for i in range(1, n + 1):
        t = subprocess.run(["pdftotext", "-f", str(i), "-l", str(i), "-raw", pdf, "-"],
                           capture_output=True, text=True).stdout
        out.append(norm(t))
    return out


def locate_pages(c, pdf):
    pages = page_texts(pdf)
    for group in (c.keys, c.extras):
        for name, kv in group.items():
            q = kv.get("quote")
            if not q:
                continue
            probe = norm(q)[:50]
            hit = [i + 1 for i, t in enumerate(pages) if probe in t]
            if not hit:
                raise RuntimeError(f"{c.cid}: quote for {name} not found in rendered PDF: {q[:60]}")
            kv["page"] = hit[0]
    for d in c.distractors:
        probe = norm(d["quote"])[:50]
        hit = [i + 1 for i, t in enumerate(pages) if probe in t]
        if not hit:
            raise RuntimeError(f"{c.cid}: distractor not found: {d['quote'][:60]}")
        d["page"] = hit[0]
    return len(pages)


# --------------------------------------------------------------------------
# Contract A: fair
# --------------------------------------------------------------------------
def contract_A():
    c = Contract("A", "Creator Partnership Agreement: Northwind Athletics and Maya Okafor", "northwind",
                 "maya_okafor", "rights_protective",
                 "Fair contract close to the brand's playbook. A good system should flag little or nothing.",
                 "contract_A_northwind_maya.pdf")
    parties_block(c, "northwind", "maya_okafor", "November 3, 2026")
    c.sec(1, "Campaign and Deliverables",
          "Brand engages Creator to produce and publish content for Brand's “Run the Block” campaign (the "
          "“Campaign”), consisting of three (3) Instagram Reels and two (2) Instagram Story sets (the "
          "“Deliverables”), as described in Schedule A. The kickoff call will take place on November 10, 2026 "
          "(the “Kickoff Date”). Creator shall publish the Deliverables between December 1 and December 20, 2026.")
    c.sec(2, "Fee", c.k("fee", "Brand shall pay Creator a flat fee of $4,000.00 (the “Fee”) for the Deliverables.",
                        value=4000, unit="usd", status="found", risk=1, deviates_from_playbook=False,
                        direction="neutral", note="100% of the creator's standard package rate ($4,000)."))
    c.sec(3, "Payment",
          c.k("payment_terms", "Brand shall pay fifty percent (50%) of the Fee within five (5) business days of signature, "
              "and the balance within thirty (30) days of Brand's receipt of Creator's invoice following publication of the "
              "final Deliverable.", value=30, unit="net_days", status="found", risk=1, deviates_from_playbook=False,
              direction="neutral", note="50% on signature, balance net-30. Late interest of 1.5% per month is favorable."),
          "Overdue amounts accrue interest at one and one-half percent (1.5%) per month.")
    c.sec(4, "License",
          c.k("usage_rights", "Creator grants Brand a non-exclusive license to use the Deliverables for twelve (12) months "
              "from first publication of each Deliverable, on Brand's owned social media channels and as paid partnership ads, "
              "in the United States and Canada.", value=12, unit="months", status="found", risk=2,
              deviates_from_playbook=True, direction="unfavorable",
              note="Term matches the playbook; territory adds Canada (minor)."),
          "Whitelisting and dark posting through Creator's account are not included and require a separate written "
          "agreement and fee. Creator retains ownership of all Content.")
    c.sec(5, "Exclusivity",
          c.k("exclusivity", "From the Effective Date until three (3) months after the final Deliverable is published, "
              "Creator shall not publish paid promotion for a direct competitor of Brand in athletic footwear or apparel.",
              value=3, unit="months", status="found", risk=1, deviates_from_playbook=False, direction="neutral",
              note="Limited to direct competitors in the category."),
          "The competitors covered are listed in Schedule B.")
    c.sec(6, "Revisions",
          c.k("revisions", "Brand may request up to two (2) rounds of revisions per Deliverable, delivered as consolidated "
              "feedback within three (3) business days of delivery.", value=2, unit="rounds", status="found", risk=1,
              deviates_from_playbook=False, direction="neutral", note="Extra rounds billed at $150 per hour."),
          "Additional rounds will be billed at $150 per hour.")
    c.sec(7, "Approval",
          c.k("content_approval", "Brand shall approve or provide written feedback on each Deliverable within three (3) "
              "business days of receipt. A Deliverable is deemed approved if Brand does not respond within five (5) business days.",
              value=dict(respond_days=3, deemed_approval_days=5), unit="business_days", status="found", risk=1,
              deviates_from_playbook=False, direction="neutral", note="Approval cannot be unreasonably withheld."),
          "Brand shall not unreasonably withhold approval.")
    c.sec(8, "Disclosure",
          c.extra("disclosure", "Creator shall disclose the partnership using #ad or Instagram's paid partnership label, "
                  "in accordance with the FTC Endorsement Guides.", value="required", risk=1, note="Compliant."))
    c.sec(9, "Cancellation",
          c.k("kill_fee", "If Brand cancels the Campaign after the Kickoff Date and before the final Deliverable is published, "
              "Brand shall pay Creator a cancellation fee equal to twenty-five percent (25%) of the Fee, in addition to any "
              "amounts already paid.", value=25, unit="percent", status="found", risk=1, deviates_from_playbook=False,
              direction="neutral", note=""))
    c.sec(10, "Termination",
          c.k("termination", "Either party may terminate this Agreement on fourteen (14) days' written notice. Creator shall "
              "be paid for all work completed through the termination date.", value=14, unit="days", status="found",
              risk=1, deviates_from_playbook=False, direction="neutral", note="Mutual."))
    c.sec(11, "General",
          "Creator is an independent contractor. Each party shall keep the other's non-public information confidential. "
          "This Agreement is governed by the laws of the State of Oregon and is the entire agreement between the parties "
          "on its subject.")
    signature(c, "northwind", "maya_okafor")
    c.pagebreak()
    c.h("Schedule A: Deliverables")
    c.tbl([["Deliverable", "Format", "Posting window"],
           ["Reel 1", "Instagram Reel, 20-30 seconds", "Dec 1 - Dec 6, 2026"],
           ["Reel 2", "Instagram Reel, 20-30 seconds", "Dec 7 - Dec 13, 2026"],
           ["Reel 3", "Instagram Reel, 20-30 seconds", "Dec 14 - Dec 20, 2026"],
           ["Story set 1", "5 frames with link sticker", "Dec 1 - Dec 10, 2026"],
           ["Story set 2", "5 frames with link sticker", "Dec 11 - Dec 20, 2026"]],
          [1.5 * inch, 2.9 * inch, 2.2 * inch])
    c.h("Schedule B: Covered competitors")
    c.p("Stridewell, Apex Stride, Lumen Run, Granite Footwear, Halcyon Sport, Trailhound, Pacepoint, Velocity Lane.")
    c.distractors.append(dict(
        label="Late-payment interest is not a payment term",
        quote="Overdue amounts accrue interest at one and one-half percent (1.5%) per month."))
    c.as_written = dict(fee_mult=1.0, usage_months=12, excl_months=3, net_days=30, kill_pct=25, revisions=2)
    c.interpretation = "as written"
    return c


# --------------------------------------------------------------------------
# Contract B: predatory
# --------------------------------------------------------------------------
def contract_B():
    c = Contract("B", "Creator Partnership Agreement: Vela Beauty and Priya Nair", "vela", "priya_nair",
                 "rights_protective",
                 "Predatory contract. Eight planted traps, each stated plainly. A good system should flag all of them.",
                 "contract_B_vela_priya.pdf")
    parties_block(c, "vela", "priya_nair", "November 5, 2026")
    c.sec(1, "Campaign and Term",
          "Brand engages Creator for Brand's “Glow Season” campaign (the “Campaign”), consisting of two (2) "
          "Reels, one (1) carousel post and three (3) Story frames (the “Deliverables”). The “Term” of this "
          "Agreement is December 1, 2026 through February 28, 2027.")
    c.sec(2, "Fee",
          c.k("fee", "Brand shall pay Creator a total fee of $4,500.00 (the “Fee”), which is inclusive of all rights "
              "granted under this Agreement, whitelisting, paid media amplification, raw footage and any additional content "
              "Brand may request.", value=4500, unit="usd", status="found", risk=4, deviates_from_playbook=True,
              direction="unfavorable",
              note="75% of the creator's standard rate ($6,000) and bundles extras that normally cost extra."))
    c.sec(3, "Payment",
          c.k("payment_terms", "Brand shall pay the Fee within ninety (90) days after the conclusion of the Campaign.",
              value=90, unit="net_days", status="found", risk=4, deviates_from_playbook=True, direction="unfavorable",
              note="Net-90 and no advance."))
    c.sec(4, "License",
          c.k("usage_rights", "Creator grants Brand a perpetual, irrevocable, worldwide license to use, edit and create "
              "derivative works from the Content in all media now known or later developed, including paid media, "
              "whitelisting and dark posts through Creator's account, and the use of Creator's name, voice and likeness, "
              "including in AI-generated or AI-modified content.", value=USAGE_PERPETUAL, unit="months", status="found",
              risk=5, deviates_from_playbook=True, direction="unfavorable",
              note="Perpetual, irrevocable, worldwide, includes whitelisting and AI likeness."))
    c.sec(5, "Exclusivity",
          c.k("exclusivity", "For twelve (12) months from the Effective Date, Creator shall not create, publish or promote any "
              "content for any brand in the beauty, skincare, haircare, wellness or personal care categories.",
              value=12, unit="months", status="found", risk=5, deviates_from_playbook=True, direction="unfavorable",
              note="Twice the playbook length and covers the creator's whole niche."))
    c.sec(6, "Revisions",
          c.k("revisions", "Creator shall make all revisions requested by Brand until Brand is satisfied in its sole "
              "discretion, at no additional charge.", value=REV_UNLIMITED, unit="rounds", status="found", risk=5,
              deviates_from_playbook=True, direction="unfavorable", note="Unlimited."))
    c.sec(7, "Approval",
          c.k("content_approval", "All Content is subject to Brand's approval in its sole discretion, which may be given or "
              "withdrawn at any time, including after publication, in which case Creator shall remove the Content within "
              "twenty-four (24) hours.", value=dict(respond_days=None, deemed_approval_days=None, revocable=True),
              unit="business_days", status="found", risk=5, deviates_from_playbook=True, direction="unfavorable",
              note="No deadline, no deemed approval, revocable after posting."))
    c.sec(8, "Disclosure",
          c.extra("disclosure", "Creator shall not include #ad, a paid partnership label or any other sponsorship disclosure "
                  "unless Brand instructs Creator to do so in writing.", value="prohibited", risk=5,
                  note="Instructs the creator not to disclose; conflicts with FTC guidance."))
    c.sec(9, "Cancellation",
          c.k("kill_fee", "Brand may cancel the Campaign at any time and for any reason without liability to Creator, and no "
              "fee shall be due for any Deliverable that Brand has not yet accepted.", value=0, unit="percent",
              status="found", risk=5, deviates_from_playbook=True, direction="unfavorable", note="No kill fee."))
    c.sec(10, "Termination",
          c.k("termination", "Brand may terminate this Agreement immediately on written notice. Creator may not terminate this "
              "Agreement. On any termination, Creator forfeits any unpaid portion of the Fee and shall refund any amount "
              "previously paid.", value=0, unit="days", status="found", risk=5, deviates_from_playbook=True,
              direction="unfavorable", note="Brand only, no notice, forfeiture and refund."))
    c.sec(11, "General",
          "Creator is an independent contractor. This Agreement is governed by the laws of the State of California and is "
          "the entire agreement between the parties on its subject.")
    signature(c, "vela", "priya_nair")
    c.as_written = dict(fee_mult=0.75, usage_months=USAGE_PERPETUAL, excl_months=12, net_days=90, kill_pct=0,
                        revisions=REV_UNLIMITED)
    c.interpretation = "as written"
    return c


# --------------------------------------------------------------------------
# Contract C: buried and ambiguous
# --------------------------------------------------------------------------
def contract_C():
    c = Contract("C", "Creator Partnership Agreement: Kettle & Co and Jordan Lee", "kettle", "jordan_lee",
                 "cash_first",
                 "Looks friendly but the traps sit in definitions and Schedule C. Three terms are ambiguous and one is missing.",
                 "contract_C_kettle_jordan.pdf")
    parties_block(c, "kettle", "jordan_lee", "November 9, 2026")
    c.sec(1, "Definitions",
          c.k("_term_def", "“Term” means the period commencing on the Effective Date and continuing for thirty-six "
              "(36) months.", status="found", risk=None, note="Definition used by the license clause."),
          c.k("_cc_def", "“Campaign Completion” means the date on which Brand has given final written approval of the "
              "last Deliverable and has received Creator's sell-through report.", status="found", risk=None,
              note="Starts the payment clock; both conditions are in Brand's control."),
          "“Category” has the meaning given in Schedule C. “Deliverables” means two (2) TikTok videos and one "
          "(1) Reel for Brand's “Snack Attack” campaign.")
    c.sec(2, "Services", "Creator shall produce and publish the Deliverables during December 2026.")
    c.sec(3, "Fee", c.k("fee", "Brand shall pay Creator the Fee set out in Schedule C.", value=2250, unit="usd",
                        status="found", risk=3, deviates_from_playbook=True, direction="unfavorable",
                        note="Amount and a 10% deduction are in Schedule C (headline $2,500, net $2,250)."))
    c.sec(4, "Payment",
          c.k("payment_terms", "Brand shall pay the Fee within thirty (30) days following Campaign Completion.",
              value=None, candidates=[30, 60, 90], unit="net_days", status="ambiguous", risk=4,
              deviates_from_playbook=True, direction="unfavorable",
              note="The 30 days start at Campaign Completion, which depends on Brand approval and a sell-through report."))
    c.sec(5, "License",
          c.k("usage_rights", "Brand may use the Deliverables on any channel, in any territory, for the Term.", value=36,
              unit="months", status="found", risk=4, deviates_from_playbook=True, direction="unfavorable",
              note="Term is defined as 36 months in Section 1; playbook norm is 6 months."))
    c.sec(6, "Exclusivity",
          c.k("exclusivity", "Creator shall observe reasonable exclusivity in the Category during the Term.", value=None,
              candidates=[3, 12, 36], unit="months", status="ambiguous", risk=4, deviates_from_playbook=True,
              direction="unfavorable", note="'Reasonable' is undefined; Category is very broad (Schedule C); Term is 36 months."))
    c.sec(7, "Revisions",
          c.k("revisions", "Creator shall make reasonable revisions requested by Brand.", value=None,
              candidates=[2, 4, REV_UNLIMITED], unit="rounds", status="ambiguous", risk=4, deviates_from_playbook=True,
              direction="unfavorable", note="No round limit."))
    c.sec(8, "Approval",
          c.k("content_approval", "Brand shall review each Deliverable within five (5) business days of receipt.",
              value=dict(respond_days=5, deemed_approval_days=None), unit="business_days", status="found", risk=3,
              deviates_from_playbook=True, direction="unfavorable", note="No deemed approval if Brand is silent."))
    c.sec(9, "Termination",
          c.k("termination", "Either party may terminate this Agreement on fourteen (14) days' written notice, and Creator shall "
              "be paid for Deliverables accepted by Brand before the termination date, less any unearned advance previously "
              "paid.", value=14, unit="days", status="found", risk=3, deviates_from_playbook=True,
              direction="unfavorable", note="Pay only for accepted Deliverables, not work completed."))
    c.nf("kill_fee", value=None, unit="percent", risk=4, deviates_from_playbook=True, direction="unfavorable",
         note="No cancellation fee clause anywhere in the agreement.")
    c.sec(10, "Warranty and liability",
          "Creator warrants that the Deliverables are original for a period of twelve (12) months after publication. "
          "Brand's total liability under this Agreement shall not exceed $5,000.")
    c.distractors.append(dict(label="12 months is a warranty period, not usage or exclusivity",
                              quote="Creator warrants that the Deliverables are original for a period of twelve (12) months"))
    c.distractors.append(dict(label="$5,000 is Brand's liability cap, not a fee",
                              quote="Brand's total liability under this Agreement shall not exceed $5,000."))
    c.sec(11, "General",
          "Creator is an independent contractor. This Agreement is governed by the laws of the State of Texas and is the "
          "entire agreement between the parties on its subject.")
    signature(c, "kettle", "jordan_lee")
    c.pagebreak()
    c.h("Schedule C: Commercial terms")
    c.p(c.k("_fee_sched", "Fee: $2,500.00, less a platform and affiliate administration fee of ten percent (10%) retained by "
            "Brand, for a net payment of $2,250.00.", status="found", risk=None, note="Where the fee deduction appears."))
    c.p(c.k("_cat_sched", "“Category” means any packaged food or beverage product, including snacks, beverages, "
            "confectionery and supplements.", status="found", risk=None, note="Where the exclusivity scope is defined."))
    c.as_written = dict(fee_mult=0.9, usage_months=36, excl_months=36, net_days=90, kill_pct=0, revisions=REV_UNLIMITED)
    c.interpretation = "ambiguous terms mapped to the worst case for the creator; missing kill fee mapped to 0%"
    return c


# --------------------------------------------------------------------------
# Contract D: clean source (the scan is derived from this)
# --------------------------------------------------------------------------
def contract_D():
    c = Contract("D", "Creator Partnership Agreement: Northwind Athletics and Diego Ramirez", "northwind",
                 "diego_ramirez", "balanced",
                 "Messy scan of a printed agreement with handwritten changes, one illegible term and one unclear note.",
                 "contract_D_northwind_diego_SCAN.pdf")
    parties_block(c, "northwind", "diego_ramirez", "November 4, 2026")
    c.sec(1, "Campaign and Deliverables",
          "Brand engages Creator to produce and publish content for Brand's “Run the Block” campaign (the "
          "“Campaign”), consisting of two (2) Instagram Reels and three (3) Instagram Story frames (the "
          "“Deliverables”). The kickoff call will take place on November 11, 2026 (the “Kickoff Date”). "
          "Creator shall publish the Deliverables between December 2 and December 21, 2026.")
    c.sec(2, "Fee", c.k("fee", "Brand shall pay Creator a flat fee of $3,200.00 (the “Fee”) for the Deliverables.",
                        value=3200, unit="usd", status="found", risk=1, deviates_from_playbook=False,
                        direction="neutral", note="100% of the creator's standard rate."))
    c.sec(3, "Payment",
          c.k("payment_terms", "Brand shall pay fifty percent (50%) of the Fee on signature and the balance within thirty (30) "
              "days of Brand's receipt of Creator's invoice.", value=60, unit="net_days", status="found", risk=3,
              deviates_from_playbook=True, direction="unfavorable",
              note="Printed net-30 is struck through; handwritten 'sixty (60)' with the note 'per call w/ M.R. 11/4' "
                   "and initials DR. Effective term is net-60."))
    c.sec(4, "License",
          c.k("usage_rights", "Creator grants Brand a non-exclusive license to use the Deliverables for twelve (12) months from "
              "first publication, on Brand's owned social media channels and as paid partnership ads, in the United States.",
              value=12, unit="months", status="found", risk=1, deviates_from_playbook=False, direction="neutral",
              note="Printed and unmarked."),
          "Whitelisting is not included. Creator retains ownership of all Content.")
    c.sec(5, "Exclusivity",
          c.k("exclusivity", "For three (3) months after the final Deliverable is published, Creator shall not publish paid "
              "promotion for a direct competitor of Brand in athletic footwear or apparel.", value=None, candidates=[3, 6],
              unit="months", status="ambiguous", risk=2, deviates_from_playbook=True, direction="unfavorable",
              note="Printed 'three (3) months' is not struck out, but a handwritten margin note reads '6 mo?? ask legal'. "
                   "Unclear whether the term was changed."))
    c.sec(6, "Revisions",
          c.k("revisions", "Brand may request up to two (2) rounds of revisions per Deliverable at no additional charge.",
              value=3, unit="rounds", status="found", risk=2, deviates_from_playbook=True, direction="unfavorable",
              note="Printed 'two (2)' is struck through; handwritten '3' with initials DR."))
    c.sec(7, "Approval",
          c.k("content_approval", "Brand shall approve or provide written feedback within three (3) business days of receipt. "
              "A Deliverable is deemed approved if Brand does not respond within five (5) business days.",
              value=dict(respond_days=3, deemed_approval_days=5), unit="business_days", status="found", risk=1,
              deviates_from_playbook=False, direction="neutral", note="Printed and unmarked."))
    c.sec(8, "Disclosure",
          c.extra("disclosure", "Creator shall disclose the partnership using #ad or Instagram's paid partnership label.",
                  value="required", risk=1, note="Compliant."))
    c.sec(9, "Cancellation",
          c.k("kill_fee", "If Brand cancels the Campaign after the Kickoff Date, Brand shall pay Creator a cancellation fee equal "
              "to twenty-five percent (25%) of the Fee.", value=None, candidates=[], unit="percent", status="ambiguous",
              risk=None, deviates_from_playbook=None, direction=None,
              note="The percentage is obscured by a coffee stain in the scan. The clean source says 25%, but a model reading "
                   "only the scan should report that it cannot read the figure."))
    c.sec(10, "Termination",
          c.k("termination", "Either party may terminate this Agreement on fourteen (14) days' written notice. Creator shall be "
              "paid for all work completed through the termination date.", value=14, unit="days", status="found", risk=1,
              deviates_from_playbook=False, direction="neutral", note="Printed and unmarked."))
    c.sec(11, "General",
          "Creator is an independent contractor. This Agreement is governed by the laws of the State of Oregon and is the "
          "entire agreement between the parties on its subject.")
    signature(c, "northwind", "diego_ramirez")
    c.h("Schedule A: Deliverables")
    c.tbl([["Deliverable", "Format", "Posting window"],
           ["Reel 1", "Instagram Reel, 20-30 seconds", "Dec 2 - Dec 9, 2026"],
           ["Reel 2", "Instagram Reel, 20-30 seconds", "Dec 10 - Dec 17, 2026"],
           ["Story frames 1-3", "3 frames with link sticker", "Dec 2 - Dec 21, 2026"]],
          [1.5 * inch, 2.9 * inch, 2.2 * inch])
    c.as_written = dict(fee_mult=1.0, usage_months=12, excl_months=6, net_days=60, kill_pct=25, revisions=3)
    c.interpretation = ("handwritten changes applied; exclusivity mapped to 6 months (worst case); "
                        "obscured kill fee mapped to the 25% printed in the clean source")
    return c


# --------------------------------------------------------------------------
# Scan simulation for contract D
# --------------------------------------------------------------------------
INK = (28, 52, 150)
DPI = 170


def word_boxes(pdf, page):
    out = subprocess.run(["pdftotext", "-bbox", "-f", str(page), "-l", str(page), pdf, "-"],
                         capture_output=True, text=True).stdout
    words = []
    for m in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', out):
        x0, y0, x1, y1, w = m.groups()
        words.append((float(x0), float(y0), float(x1), float(y1), html.unescape(w)))
    return words


def clean_tok(w):
    return re.sub(r"[.,;:]+$", "", w).lower()


def find_seq(words, tokens, start=0):
    toks = [clean_tok(t) for t in tokens]
    for i in range(start, len(words) - len(toks) + 1):
        if all(clean_tok(words[i + j][4]) == toks[j] for j in range(len(toks))):
            return i
    return None


def bbox_of(words, i, n):
    seg = words[i:i + n]
    return (min(w[0] for w in seg), min(w[1] for w in seg), max(w[2] for w in seg), max(w[3] for w in seg))


def ink_text(img, text, xy, size, angle, rng):
    font = ImageFont.truetype(FONT_DIR + "DejaVuSans-Oblique.ttf", size)
    tmp = Image.new("RGBA", (int(size * len(text) * 0.75) + 30, int(size * 2.2)), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    x = 8
    for ch in text:
        d.text((x, 12 + rng.randint(-2, 2)), ch, font=font, fill=INK + (235,))
        x += font.getlength(ch) + rng.uniform(-0.6, 0.8)
    tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(tmp, (int(xy[0]), int(xy[1])))


def strike(img, box, rng):
    x0, y0, x1, y1 = box
    ym = (y0 + y1) / 2
    d = ImageDraw.Draw(img)
    pts = []
    n = max(6, int((x1 - x0) / 12))
    for i in range(n + 1):
        pts.append((x0 - 4 + (x1 - x0 + 8) * i / n, ym + rng.uniform(-2.5, 2.5)))
    d.line(pts, fill=INK + (240,), width=3)


def stain(img, box, rng):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w = (x1 - x0) * 1.05
    h = max((y1 - y0) * 3.0, 80)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for k in range(9):
        f = 1 - k * 0.05
        a = 90 + k * 20
        d.ellipse([cx - w * f + rng.randint(-6, 6), cy - h * f + rng.randint(-6, 6),
                   cx + w * f + rng.randint(-6, 6), cy + h * f + rng.randint(-6, 6)],
                  fill=(112, 74, 34, min(a, 250)))
    d.ellipse([cx - w * 0.9, cy - h * 0.5, cx + w * 0.9, cy + h * 0.5], fill=(104, 68, 30, 255))
    d.ellipse([cx - w * 1.05, cy - h * 1.05, cx + w * 1.05, cy + h * 1.05], outline=(92, 58, 24, 190), width=5)
    layer = layer.filter(ImageFilter.GaussianBlur(3))
    img.alpha_composite(layer)


def degrade(img, angle, rng_np, edge_shadow=True):
    img = img.convert("RGB")
    arr = np.asarray(img).astype(np.float32)
    h, w, _ = arr.shape
    arr = arr * 0.93 + np.array([14, 11, 5], dtype=np.float32)          # warm paper tone, lower contrast
    if edge_shadow:
        grad = np.linspace(1.0, 0.0, int(w * 0.09))[None, :, None]
        arr[:, :grad.shape[1], :] *= (0.80 + 0.20 * (1 - grad))
    arr += rng_np.normal(0, 7, arr.shape)                                 # sensor noise
    for _ in range(140):                                                  # dust specks
        x, y = rng_np.integers(0, w), rng_np.integers(0, h)
        r = rng_np.integers(1, 3)
        arr[max(0, y - r):y + r, max(0, x - r):x + r, :] *= 0.55
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    img = img.rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(196, 194, 188))
    return img


def make_scan(clean_pdf, out_pdf, pages_dir):
    rng = random.Random(SEED)
    rng_np = np.random.default_rng(SEED)
    os.makedirs(pages_dir, exist_ok=True)
    tmpdir = os.path.join(pages_dir, "_tmp")
    os.makedirs(tmpdir, exist_ok=True)
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", clean_pdf, os.path.join(tmpdir, "p")], check=True)
    files = sorted(f for f in os.listdir(tmpdir) if f.endswith(".png"))
    scale = DPI / 72.0
    angles = [1.4, -1.1, 0.8, -0.6]
    out_imgs = []
    for pi, f in enumerate(files, start=1):
        img = Image.open(os.path.join(tmpdir, f)).convert("RGBA")
        words = word_boxes(clean_pdf, pi)
        W, H = img.size

        def sc(b):
            return tuple(v * scale for v in b)

        # payment: strike "thirty (30)", write "sixty (60)", margin note
        i = find_seq(words, ["balance", "within", "thirty", "(30)"])
        if i is not None:
            box = sc(bbox_of(words, i + 2, 2))
            strike(img, box, rng)
            ink_text(img, "sixty (60)", (box[0] - 6, box[1] - 38), 27, 3, rng)
            ink_text(img, "per call", (W - 168, box[1] - 10), 21, -4, rng)
            ink_text(img, "w/ M.R. 11/4", (W - 172, box[1] + 14), 21, -4, rng)
            ink_text(img, "DR", (W - 120, box[1] + 44), 22, -6, rng)
        # revisions: strike "two (2)", write 3
        i = find_seq(words, ["up", "to", "two", "(2)", "rounds"])
        if i is not None:
            box = sc(bbox_of(words, i + 2, 2))
            strike(img, box, rng)
            ink_text(img, "3", (box[0] + 8, box[1] - 36), 32, 4, rng)
            ink_text(img, "DR", (W - 120, box[1] - 2), 22, -5, rng)
        # exclusivity: margin note, no strike
        i = find_seq(words, ["for", "three", "(3)", "months", "after", "the", "final"])
        if i is not None:
            box = sc(bbox_of(words, i + 1, 3))
            ink_text(img, "6 mo??", (W - 168, box[1] - 8), 24, 5, rng)
            ink_text(img, "ask legal", (W - 172, box[1] + 20), 21, 5, rng)
        # kill fee: coffee stain over the percentage
        i = find_seq(words, ["twenty-five", "percent", "(25%)"])
        if i is not None and "cancels" in " ".join(w[4] for w in words[max(0, i - 25):i]):
            stain(img, sc(bbox_of(words, i, 3)), rng)
        # small coffee ring in a corner of page 1 and a fold line on page 2
        if pi == 1:
            d = ImageDraw.Draw(img)
            d.ellipse([W - 330, H - 330, W - 130, H - 130], outline=(150, 112, 70, 90), width=7)
        if pi == 2:
            d = ImageDraw.Draw(img)
            d.line([(0, int(H * 0.36)), (W, int(H * 0.36) + 4)], fill=(170, 168, 160, 90), width=3)
        scanned = degrade(img.convert("RGB"), angles[(pi - 1) % len(angles)], rng_np)
        jpg = os.path.join(pages_dir, f"page_{pi}.jpg")
        scanned.save(jpg, "JPEG", quality=58)
        out_imgs.append(Image.open(jpg).convert("RGB"))
    out_imgs[0].save(out_pdf, "PDF", save_all=True, append_images=out_imgs[1:], resolution=DPI)
    for f in os.listdir(tmpdir):
        os.remove(os.path.join(tmpdir, f))
    os.rmdir(tmpdir)
    return len(out_imgs)


# --------------------------------------------------------------------------
# Ground-truth counter-offers
# --------------------------------------------------------------------------
def counter_truth(contracts):
    grid = list(iter_grid())
    rows = []
    for c in contracts:
        o = c.as_written
        e = brand_eval(c.brand, o)
        u = creator_utility(c.persona, o)
        ev_now = round(e["p_accept"] * u, 4)
        best = None
        for g in grid:
            ge = brand_eval(c.brand, g)
            gu = creator_utility(c.persona, g)
            gev = ge["p_accept"] * gu
            if best is None or gev > best[0]:
                best = (gev, g, ge, gu)
        gev, g, ge, gu = best
        row = dict(contract_id=c.cid, brand=c.brand, creator=c.creator, creator_persona=c.persona,
                   interpretation=c.interpretation,
                   asw_fee_mult=round(o["fee_mult"], 3), asw_usage_months=o["usage_months"],
                   asw_excl_months=o["excl_months"], asw_net_days=o["net_days"], asw_kill_pct=o["kill_pct"],
                   asw_revisions=o["revisions"], asw_p_accept=e["p_accept"], asw_creator_utility=u,
                   asw_expected_value=ev_now,
                   best_offer_text=offer_text(g), best_fee_mult=g["fee_mult"], best_usage_months=g["usage_months"],
                   best_excl_months=g["excl_months"], best_net_days=g["net_days"], best_kill_pct=g["kill_pct"],
                   best_revisions=g["revisions"], best_p_accept=ge["p_accept"], best_creator_utility=gu,
                   best_expected_value=round(gev, 4), value_recovered=round(gev - ev_now, 4))
        rows.append(row)
    return rows


def main():
    os.makedirs(path("answer_keys"), exist_ok=True)
    contracts = [contract_A(), contract_B(), contract_C(), contract_D()]
    index = []
    for c in contracts:
        clean_out = path("contracts", c.filename) if c.cid != "D" else path("answer_keys", "contract_D_clean_source.pdf")
        render_pdf(c, clean_out)
        npages = locate_pages(c, clean_out)
        if c.cid == "D":
            scan_pages = make_scan(clean_out, path("contracts", c.filename), path("contracts", "contract_D_scan_pages"))
            assert scan_pages == npages
        cr, br = CREATORS[c.creator], BRANDS[c.brand]
        fields = {f: c.keys[f] for f in FIELDS}
        helper = {k: v for k, v in c.keys.items() if k.startswith("_")}
        flagged = [f for f in FIELDS if isinstance(fields[f].get("risk"), int) and fields[f]["risk"] >= 4]
        key = dict(contract_id=c.cid, file=f"contracts/{c.filename}", pages=npages, brand=br["name"], brand_id=c.brand,
                   creator=cr["name"], creator_standard_package_fee_usd=cr["baseline_fee"], scenario=c.scenario,
                   fields=fields, extras=c.extras, helper_quotes=helper, distractors=c.distractors,
                   expected_flagged_fields=flagged, creator_persona=c.persona,
                   as_written_terms=c.as_written, as_written_interpretation=c.interpretation,
                   notes=("deviates_from_playbook is judged against the brand's own playbook for fee, usage_rights, "
                          "exclusivity, payment_terms, kill_fee and revisions. For termination and content_approval it is "
                          "judged against clauses/norm_reference.json."))
        write_json(path("answer_keys", f"contract_{c.cid}_key.json"), key)
        index.append(dict(contract_id=c.cid, file=c.filename, scenario=c.scenario, brand=br["name"], creator=cr["name"],
                          pages=npages, input_type="scanned image PDF (no text layer)" if c.cid == "D" else "text PDF",
                          expected_flagged=",".join(flagged) if flagged else "none"))
        print(f"contract {c.cid}: {npages} pages, flagged {flagged}")
    write_csv(path("contracts", "contracts_index.csv"), index)
    truth = counter_truth(contracts)
    write_csv(path("answer_keys", "contract_counter_truth.csv"), truth)
    for t in truth:
        print(t["contract_id"], "as-written EV", t["asw_expected_value"], "best EV", t["best_expected_value"],
              "recovered", t["value_recovered"], "|", t["best_offer_text"])


if __name__ == "__main__":
    main()
