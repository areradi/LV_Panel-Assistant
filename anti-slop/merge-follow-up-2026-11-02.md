# بررسی پس از ادغام

Mode: after (session override). Scope: recovery and integration of the two existing versions.
Direction: existing DESIGN.md and the user's three-column desktop reference. No new visual assets.

- Preserved the existing desktop layout, Persian RTL, EN/DE translations and stale-result guards.
- Fixed the actual In/design-current mismatch in the persistent summary and labeled W/H/D in mm.
- Preserved unknown poles and protection settings rather than synthesizing product facts.
- Fixed visible Tk boxes caused by Unicode isolation controls; confirmed the rebuilt executable visually.
- Checked FA/EN/DE screens and light/dark appearance; automated GUI regression tests also ran.
- Kept the contextual preview and formula drawer; no unapproved preview replacement or formula-page redesign.
- Preserved the disabled DXF/EPLAN export decisions and tested their absence.
- Delivery limitation: browser-dependent PDF conversion could not be verified successfully in the restricted runtime.

The delivery gate is limited to observed integration behavior. All display sizes, DPI settings,
keyboard paths and engineering compliance have not been exhaustively verified. Detailed test results
and the unresolved PDF test are recorded in docs/MERGE_REPORT.md.
