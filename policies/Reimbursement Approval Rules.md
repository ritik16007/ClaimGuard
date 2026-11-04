# Reimbursement Approval Rules — fictional MVP policy

> Fictional sample policy for the ClaimGuard demonstration. INR throughout.

## Page 1: Decision outcomes

The policy engine returns auto-approved, pending authority review, or rejected. It never sends money. Auto-approved claims enter the authority payment queue. Reviewed claims enter that queue only after an authority approves them.

## Page 2: Automatic approval

Auto-approval is limited to known categories at or below their stated cap, with readable receipt evidence, matching dates and amounts, a timely submission, and no duplicate or risk flag. One failed prerequisite prevents auto-approval.

## Page 3: Authority review

Unknown categories, amounts above an auto-approval cap, uncertain OCR, possible duplicates, late submissions, mixed bills, and policy exceptions are routed to an authority. A manager or authority reviews those claims and may approve or reject them with a recorded reason.

## Page 4: Direct rejection and duplicate checks

An exact receipt-file duplicate already recorded in the database is rejected. Duplicate claim submissions using that exact file are rejected and logged. Clearly invalid amounts or dates, and attempts to override controls or demand an unauthorised payment, are also rejected. The system records the file's SHA-256 fingerprint and checks it before processing a repeat. A different file that may represent the same purchase is held for human review. OCR is an aid: uncertainty triggers review and is never described as genuine verification.

## Page 5: Authority payment queue

Auto-approved claims and authority-approved claims appear in the payment queue. An authority may record a demo payment confirmation there. This action changes the demo record only; no bank, payroll, or payment provider is connected. ClaimGuard does not trigger a bank payout or transfer; only an authority can record a demo confirmation.
