"""Builds the labeled clause benchmark: 8 clause types x 14 clauses = 112 clauses.

Labels are relative to the Northwind Athletics playbook (the reference brand).
risk_score is from the creator's point of view:
  1 standard or better for the creator   2 minor concern   3 notable, negotiate
  4 high, likely harmful                 5 severe, do not sign as written
deviates_from_norm = the clause differs from the Northwind standard term, in either direction.
"""
import json
from common import path, write_csv, write_json

NORMS = {
    "fee": "Fee between 90% and 110% of the creator's standard package rate (baseline for this benchmark: $4,000).",
    "usage_rights": "12 months from first publication, owned channels plus paid partnership ads, United States only, no whitelisting without a separate fee, no perpetual or ownership grants.",
    "exclusivity": "3 months after the final Deliverable, direct competitors in athletic footwear and apparel only.",
    "payment_terms": "50% on signature, balance net-30 from invoice.",
    "kill_fee": "25% of the Fee if Brand cancels after the kickoff date.",
    "revisions": "Two rounds of revisions per Deliverable at no extra charge.",
    "termination": "Either party may terminate on 14 days' written notice; Creator is paid for work completed.",
    "content_approval": "Brand responds within 3 business days; Content is deemed approved after 5 business days; approval is not unreasonably withheld; sponsorship disclosure follows FTC guidance.",
}
PREFIX = {"fee": "FEE", "usage_rights": "USE", "exclusivity": "EXC", "payment_terms": "PAY",
          "kill_fee": "KIL", "revisions": "REV", "termination": "TRM", "content_approval": "APR"}

# (text, risk, deviates, direction, difficulty, style, parsed_value)
C = {}

C["fee"] = [
    ("Brand shall pay Creator a flat fee of $4,000.00 for the Deliverables described in Schedule A.", 1, False, "neutral", "easy", "plain", "4000"),
    ("In consideration for the Deliverables, Brand will pay Creator a fee of $4,400.", 1, False, "favorable", "easy", "plain", "4400"),
    ("Creator's fee for the Campaign is $3,600, payable as set out in Section 3.", 2, False, "unfavorable", "medium", "plain", "3600"),
    ("The fee payable to Creator for all Deliverables shall be $3,000.", 3, True, "unfavorable", "easy", "plain", "3000"),
    ("Creator shall receive a one-time fee of $2,000 for the Deliverables.", 4, True, "unfavorable", "easy", "plain", "2000"),
    ("Creator's compensation shall be product credit with a retail value of $4,000, redeemable on Brand's website within 12 months.", 5, True, "unfavorable", "medium", "plain", "0"),
    ("The Fee of $4,000 is inclusive of all usage rights, whitelisting, paid media amplification and delivery of all raw footage, for which Creator shall not be entitled to any additional payment.", 4, True, "unfavorable", "hard", "buried", "4000"),
    ("Brand shall pay Creator $5,200 for the Deliverables.", 1, True, "favorable", "easy", "plain", "5200"),
    ("Brand will pay a base fee of $4,000, plus a $500 bonus if any Reel exceeds 50,000 views within 14 days of posting.", 1, True, "favorable", "medium", "plain", "4000"),
    ("Brand shall pay Creator $4,000, less a fifteen percent (15%) platform administration fee retained by Brand.", 4, True, "unfavorable", "hard", "legalese", "3400"),
    ("Fee: $1,333.33 per Deliverable, for three (3) Deliverables.", 1, False, "neutral", "medium", "numeric", "4000"),
    ("The parties shall agree in good faith on Creator's compensation following delivery of the Content.", 5, True, "unfavorable", "medium", "ambiguous", "AMBIGUOUS"),
    ("Brand will pay Creator $4,000, provided that Brand may withhold up to twenty percent (20%) of the fee pending its satisfaction with campaign performance metrics.", 4, True, "unfavorable", "hard", "buried", "3200"),
    ("Creator shall be paid $3,900, being $1,300 per Deliverable.", 1, False, "neutral", "hard", "numeric", "3900"),
]

C["usage_rights"] = [
    ("Creator grants Brand a non-exclusive license to use the Deliverables for twelve (12) months from first publication on Brand's owned social channels and as paid partnership ads, in the United States.", 1, False, "neutral", "easy", "plain", "12"),
    ("Brand may repost the Deliverables on its owned channels for six (6) months from first publication, in the United States.", 1, True, "favorable", "easy", "plain", "6"),
    ("Creator grants Brand a non-exclusive license for twelve (12) months to use the Deliverables on its owned channels and as paid partnership ads, worldwide.", 2, True, "unfavorable", "medium", "plain", "12"),
    ("The license granted in this Section shall continue for twenty-four (24) months from first publication.", 3, True, "unfavorable", "easy", "plain", "24"),
    ("Creator grants Brand a perpetual, irrevocable, worldwide license to use the Content in all media.", 5, True, "unfavorable", "easy", "plain", "999"),
    ("Brand may reproduce, distribute, display and otherwise exploit the Content in any channel, territory or format, and Creator acknowledges that the rights granted hereunder are granted in perpetuity and are not subject to termination for any reason.", 5, True, "unfavorable", "hard", "buried", "999"),
    ("Brand's license to the Content shall last for the Term, as defined in Section 1, which is a period of thirty-six (36) months from the Effective Date.", 4, True, "unfavorable", "hard", "buried", "36"),
    ("Creator grants Brand a limited license to share the Content on Brand's organic social channels for ninety (90) days.", 1, True, "favorable", "medium", "plain", "3"),
    ("Brand may use the Content for twelve (12) months, including whitelisting and dark posts through Creator's account, at no additional charge.", 3, True, "unfavorable", "medium", "plain", "12"),
    ("All Content, and all intellectual property rights in it, is a work made for hire and shall be owned exclusively by Brand upon creation.", 5, True, "unfavorable", "medium", "legalese", "999"),
    ("The license runs for twelve (12) months from first publication and renews automatically for successive twelve (12) month periods unless Brand elects not to renew by written notice.", 4, True, "unfavorable", "hard", "buried", "999"),
    ("Brand may use the Content on its owned channels for twelve (12) months. Any paid amplification requires Creator's written consent and a separate fee.", 1, True, "favorable", "medium", "plain", "12"),
    ("Brand may edit, alter and create derivative works from the Content, including AI-generated or AI-modified versions using Creator's name, voice and likeness.", 5, True, "unfavorable", "medium", "legalese", "999"),
    ("Usage period: one (1) year from first post. Owned channels and paid partnership ads. US only.", 1, False, "neutral", "easy", "informal", "12"),
]

C["exclusivity"] = [
    ("For three (3) months after the final Deliverable is published, Creator shall not publish paid promotion for a direct competitor of Brand in athletic footwear or apparel.", 1, False, "neutral", "easy", "plain", "3"),
    ("This Agreement is non-exclusive. Creator remains free to work with any other brand, including Brand's competitors.", 1, True, "favorable", "easy", "plain", "0"),
    ("Creator shall not promote any direct competitor of Brand in athletic footwear or apparel for six (6) months after the final Deliverable is published.", 2, True, "unfavorable", "easy", "plain", "6"),
    ("Creator shall not promote any direct competitor of Brand in athletic footwear or apparel for twelve (12) months after the Effective Date.", 4, True, "unfavorable", "easy", "plain", "12"),
    ("For twelve (12) months, Creator shall not create or publish sponsored content for any sportswear, fitness, nutrition, wellness or lifestyle brand.", 5, True, "unfavorable", "easy", "plain", "12"),
    ("During the Term, Creator shall not publish promotional content for any brand other than Brand.", 5, True, "unfavorable", "hard", "buried", "TERM_ALL_BRANDS"),
    ("Creator agrees to observe exclusivity in the Category for the period set out in Schedule A. 'Category' means any consumer product marketed to consumers aged 16 to 34.", 5, True, "unfavorable", "hard", "buried", "BROAD_CATEGORY"),
    ("Creator will not promote competing athletic footwear brands for ninety (90) days after posting.", 1, True, "favorable", "medium", "plain", "3"),
    ("Exclusivity runs for ninety (90) days from the final Deliverable and covers direct competitors in athletic footwear and apparel only.", 1, False, "neutral", "medium", "legalese", "3"),
    ("Creator shall observe such exclusivity as Brand may reasonably require from time to time.", 4, True, "unfavorable", "medium", "ambiguous", "AMBIGUOUS"),
    ("Creator shall not publish content for any competitor of Brand in athletic footwear or apparel in the fourteen (14) days before and after each Deliverable.", 2, True, "unfavorable", "medium", "plain", "BLACKOUT_14D"),
    ("Exclusivity lasts six (6) months, reduced to three (3) months if Brand pays any invoice more than ten (10) days late.", 3, True, "unfavorable", "hard", "buried", "6"),
    ("Creator shall be exclusive to Brand in the athletic category for twenty-four (24) months, unless Creator pays Brand a buyout of two times the Fee.", 5, True, "unfavorable", "hard", "legalese", "24"),
    ("Creator may work with non-competing brands. Direct competitors are the eight brands listed in Schedule B and are restricted for three (3) months after the final Deliverable.", 1, False, "neutral", "medium", "plain", "3"),
]

C["payment_terms"] = [
    ("Brand shall pay fifty percent (50%) of the Fee on signature and the balance within thirty (30) days of Creator's invoice.", 1, False, "neutral", "easy", "plain", "30"),
    ("Brand shall pay each invoice within fifteen (15) days of receipt.", 1, True, "favorable", "easy", "plain", "15"),
    ("Brand shall pay each invoice within forty-five (45) days of receipt.", 2, True, "unfavorable", "easy", "plain", "45"),
    ("Payment terms are net sixty (60) days from the date of Creator's invoice.", 3, True, "unfavorable", "easy", "plain", "60"),
    ("Brand shall pay the Fee within ninety (90) days after the conclusion of the Campaign.", 4, True, "unfavorable", "easy", "plain", "90"),
    ("The Fee is due within thirty (30) days following publication of the final Deliverable.", 2, False, "neutral", "medium", "plain", "30"),
    ("Brand shall pay Creator within thirty (30) days of Brand's receipt of payment from the relevant retail partner or agency.", 4, True, "unfavorable", "medium", "ambiguous", "AMBIGUOUS"),
    ("Invoices are payable net thirty (30) days from the end of the calendar month in which the Campaign concludes.", 3, True, "unfavorable", "hard", "buried", "30_EOM"),
    ("Payment shall be made upon Brand's approval of the final Content, which approval shall not be unreasonably delayed.", 3, True, "unfavorable", "medium", "ambiguous", "AMBIGUOUS"),
    ("Brand shall pay each invoice within thirty (30) days of receipt. Overdue amounts accrue interest at one and one-half percent (1.5%) per month.", 1, True, "favorable", "medium", "plain", "30"),
    ("The Fee shall be paid within thirty (30) days after Creator delivers a campaign performance report to Brand.", 2, True, "neutral", "medium", "plain", "30"),
    ("Brand shall pay within thirty (30) days of invoice, subject to completion of Brand's vendor onboarding, which Brand estimates takes sixty (60) to ninety (90) days.", 4, True, "unfavorable", "hard", "buried", "90"),
    ("Brand shall pay one hundred percent (100%) of the Fee within seven (7) days of signature.", 1, True, "favorable", "easy", "plain", "7"),
    ("Payment: net 30 days. For any invoice exceeding $5,000, payment is net 60 days.", 2, False, "neutral", "medium", "informal", "30"),
]

C["kill_fee"] = [
    ("If Brand cancels the Campaign after the Kickoff Date, Brand shall pay Creator a cancellation fee equal to twenty-five percent (25%) of the Fee.", 1, False, "neutral", "easy", "plain", "25"),
    ("If Brand cancels the Campaign for any reason after the Kickoff Date, Brand shall pay Creator fifty percent (50%) of the Fee.", 1, True, "favorable", "easy", "plain", "50"),
    ("If Brand cancels after the Kickoff Date, Creator shall be entitled to ten percent (10%) of the Fee.", 3, True, "unfavorable", "easy", "plain", "10"),
    ("Brand may cancel the Campaign at any time, for any reason, without liability to Creator.", 5, True, "unfavorable", "easy", "plain", "0"),
    ("If Brand cancels before first publication, Creator may keep any advance already paid and no further sums shall be due.", 2, True, "neutral", "medium", "plain", "ADVANCE_ONLY"),
    ("If Brand cancels for convenience, Brand shall pay Creator for Deliverables completed up to the date of cancellation, calculated pro rata.", 2, True, "neutral", "medium", "plain", "PRO_RATA"),
    ("A cancellation fee of twenty-five percent (25%) of the Fee applies only if Brand cancels more than thirty (30) days before the first scheduled posting date.", 4, True, "unfavorable", "hard", "buried", "25_CONDITIONAL"),
    ("If Brand cancels, Brand shall pay a cancellation fee of twenty-five percent (25%) of the Fee, not to exceed $500.", 4, True, "unfavorable", "hard", "buried", "12.5"),
    ("Upon cancellation by Brand after the Kickoff Date, Brand shall pay a fee of twenty-five percent (25%) of the Fee within ninety (90) days of cancellation.", 2, True, "neutral", "medium", "plain", "25"),
    ("Brand may cancel immediately if, in its sole opinion, the Content is not on-brand, in which case no fee shall be payable for any unpublished Deliverable.", 5, True, "unfavorable", "medium", "legalese", "0"),
    ("If Brand cancels after Creator submits a first draft, Brand shall pay one hundred percent (100%) of the Fee.", 1, True, "favorable", "easy", "plain", "100"),
    ("Neither party is liable for failure to perform due to a force majeure event, which includes any internal budget reallocation, reorganisation or change in marketing strategy of Brand.", 5, True, "unfavorable", "hard", "buried", "0"),
    ("Brand shall pay a cancellation fee of twenty percent (20%) of the Fee if it cancels after the Kickoff Date.", 2, True, "unfavorable", "medium", "plain", "20"),
    ("On cancellation by Brand after kickoff, Brand pays a cancellation fee equal to one quarter of the Fee.", 1, False, "neutral", "medium", "informal", "25"),
]

C["revisions"] = [
    ("Creator shall provide up to two (2) rounds of revisions per Deliverable at no additional charge.", 1, False, "neutral", "easy", "plain", "2"),
    ("Creator will make one (1) round of revisions per Deliverable.", 1, True, "favorable", "easy", "plain", "1"),
    ("Creator shall provide up to three (3) rounds of revisions per Deliverable.", 2, True, "unfavorable", "easy", "plain", "3"),
    ("Creator shall make all revisions requested by Brand until Brand is satisfied, at no additional charge.", 5, True, "unfavorable", "easy", "plain", "99"),
    ("Creator shall make reasonable revisions as requested by Brand.", 4, True, "unfavorable", "medium", "ambiguous", "AMBIGUOUS"),
    ("Two (2) rounds of revisions are included. Further rounds are billed at $150 per hour.", 1, True, "favorable", "medium", "plain", "2"),
    ("Creator shall provide two (2) rounds of revisions, provided that a round of revisions ends only when Brand confirms its approval in writing and each round may include any number of change requests.", 4, True, "unfavorable", "hard", "buried", "99"),
    ("Revisions are included in the Fee until the Content is approved by Brand and its legal department.", 4, True, "unfavorable", "medium", "plain", "99"),
    ("Two (2) rounds of revisions are included. Reshoots required by changes to Brand's brief are billed at Creator's standard day rate.", 1, True, "favorable", "medium", "plain", "2"),
    ("Brand may request revisions within fourteen (14) days of delivery, with no limit on the number of requests made in that period.", 3, True, "unfavorable", "hard", "buried", "99"),
    ("Brand is entitled to up to four (4) rounds of revisions per Deliverable.", 3, True, "unfavorable", "easy", "plain", "4"),
    ("Creator shall provide two (2) rounds of revisions and shall return each revision within twenty-four (24) hours of Brand's request.", 2, True, "unfavorable", "medium", "plain", "2"),
    ("Creator shall make up to two (2) rounds of revisions, after which Brand may reject the Content and withhold the Fee.", 4, True, "unfavorable", "hard", "legalese", "2"),
    ("Revisions: 2 rounds.", 1, False, "neutral", "easy", "informal", "2"),
]

C["termination"] = [
    ("Either party may terminate this Agreement on fourteen (14) days' written notice. Creator shall be paid for all work completed through the termination date.", 1, False, "neutral", "easy", "plain", "14"),
    ("Brand may terminate this Agreement at any time on written notice, and no amount shall be payable for work in progress.", 5, True, "unfavorable", "easy", "plain", "0"),
    ("Either party may terminate this Agreement on thirty (30) days' written notice. Creator shall be paid for work completed.", 2, True, "unfavorable", "easy", "plain", "30"),
    ("Brand may terminate for convenience on one (1) day's notice. Creator may terminate only if Brand commits a material breach that remains uncured after thirty (30) days.", 4, True, "unfavorable", "medium", "legalese", "ASYMMETRIC"),
    ("Either party may terminate on seven (7) days' written notice, and Creator shall be paid pro rata for work completed.", 1, True, "favorable", "easy", "plain", "7"),
    ("Brand may terminate this Agreement immediately if Creator's follower count on any platform falls by more than five percent (5%) at any time during the Term.", 4, True, "unfavorable", "hard", "buried", "METRIC_TRIGGER"),
    ("Brand may terminate immediately for any conduct that Brand determines in good faith to be damaging to its reputation, including conduct that occurred before the Effective Date.", 5, True, "unfavorable", "medium", "legalese", "MORALS_RETROACTIVE"),
    ("On any termination, unpaid fees are forfeited and Creator shall refund all amounts previously paid.", 5, True, "unfavorable", "easy", "plain", "FORFEIT"),
    ("Either party may terminate for an uncured material breach, ten (10) days after written notice describing the breach.", 1, True, "neutral", "medium", "legalese", "10_CAUSE_ONLY"),
    ("This Agreement renews automatically for successive twelve (12) month terms unless Creator gives notice of non-renewal by registered mail at least ninety (90) days before the renewal date.", 4, True, "unfavorable", "hard", "buried", "AUTO_RENEW"),
    ("Brand may terminate on written notice. Creator shall remove all Content from Creator's channels within twenty-four (24) hours of notice of termination.", 3, True, "unfavorable", "medium", "plain", "TAKEDOWN_24H"),
    ("Either party may terminate on fourteen (14) days' written notice, and Creator shall be paid for Deliverables accepted by Brand before the termination date.", 3, True, "unfavorable", "hard", "buried", "14_ACCEPTED_ONLY"),
    ("Creator may not terminate this Agreement for any reason before the final Deliverable is published.", 5, True, "unfavorable", "easy", "plain", "CREATOR_CANNOT"),
    ("Fourteen (14) days' written notice may be given by either party; Creator shall be compensated for work completed through the termination date.", 1, False, "neutral", "medium", "legalese", "14"),
]

C["content_approval"] = [
    ("Brand shall approve or provide written feedback within three (3) business days of receipt. Content is deemed approved if Brand does not respond within five (5) business days.", 1, False, "neutral", "easy", "plain", "3/5"),
    ("Brand shall review each Deliverable within two (2) business days of receipt.", 1, True, "favorable", "easy", "plain", "2"),
    ("Brand shall respond within seven (7) business days. There is no deemed approval.", 3, True, "unfavorable", "easy", "plain", "7/NONE"),
    ("All Content requires Brand's prior written approval before posting. Brand is not obliged to respond within any particular period.", 4, True, "unfavorable", "easy", "plain", "NO_DEADLINE"),
    ("Content is subject to Brand's approval in its sole discretion, which may be given or withdrawn at any time, including after publication.", 5, True, "unfavorable", "easy", "plain", "REVOCABLE"),
    ("Brand may require Creator to take down any Content within twenty-four (24) hours of request, for any reason.", 3, True, "unfavorable", "medium", "plain", "TAKEDOWN_24H"),
    ("Content is deemed approved if Brand has not responded within five (5) business days of submission.", 1, False, "neutral", "medium", "plain", "DEEMED_5"),
    ("Brand shall respond within a reasonable time and shall not unreasonably withhold approval.", 2, True, "neutral", "medium", "ambiguous", "AMBIGUOUS"),
    ("Creator shall give Brand fourteen (14) days to review each Deliverable before posting. Posting dates are fixed by Schedule A and cannot be moved without Brand's consent.", 3, True, "unfavorable", "hard", "buried", "14"),
    ("Creator shall not use #ad, a paid partnership label or any other sponsorship disclosure unless Brand instructs Creator to do so in writing.", 5, True, "unfavorable", "medium", "plain", "NO_DISCLOSURE"),
    ("Brand has final creative control. Creator shall not publish any Content that has not been approved in writing, and Brand may revoke an approval by written notice.", 4, True, "unfavorable", "hard", "legalese", "REVOCABLE"),
    ("Brand shall provide consolidated feedback from all of its stakeholders within three (3) business days of receipt.", 1, False, "favorable", "medium", "plain", "3"),
    ("Content is deemed approved if Brand has not responded within ten (10) business days of submission.", 2, True, "unfavorable", "medium", "plain", "10"),
    ("Creator shall follow the brand guidelines in Exhibit 1. Any deviation must be approved in writing in advance.", 2, False, "neutral", "medium", "plain", "GUIDELINES"),
]

DEV_POSITIONS = {1, 4, 6, 9, 11, 13}


def main():
    rows = []
    for ctype, items in C.items():
        assert len(items) == 14, (ctype, len(items))
        for i, (text, risk, dev, direction, diff, style, parsed) in enumerate(items, start=1):
            rows.append(dict(
                clause_id=f"{PREFIX[ctype]}-{i:02d}",
                clause_type=ctype,
                clause_text=text,
                risk_score=risk,
                deviates_from_norm="yes" if dev else "no",
                direction=direction,
                difficulty=diff,
                style=style,
                parsed_value=parsed,
                split="dev" if i in DEV_POSITIONS else "test",
                norm_reference=NORMS[ctype],
            ))
    texts = [r["clause_text"] for r in rows]
    assert len(set(texts)) == len(texts), "duplicate clause text"
    write_csv(path("clauses", "clauses_benchmark.csv"), rows)
    with open(path("clauses", "clauses_benchmark.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_json(path("clauses", "norm_reference.json"), NORMS)
    risk_counts = {k: sum(1 for r in rows if r["risk_score"] == k) for k in range(1, 6)}
    print("clauses:", len(rows), "risk distribution:", risk_counts,
          "dev:", sum(1 for r in rows if r["split"] == "dev"),
          "deviates yes:", sum(1 for r in rows if r["deviates_from_norm"] == "yes"))


if __name__ == "__main__":
    main()
