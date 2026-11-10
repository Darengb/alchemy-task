// Synthetic demo data for the preview harness (and demo recordings): a fictional operator, "Maya",
// who runs operations at a small tea brand. Nothing here comes from a real workspace.
import { addDays } from '../src/lib/dates.js'

export function demoData(today) {
  const d = (n) => addDays(today, n)
  let n = 0
  const id = () => `00000000-0000-4000-8000-${String(++n).padStart(12, '0')}`
  const T = (title, area, offset, extra = {}) => {
    const date = offset === null ? null : d(offset)
    return {
      task_id: id(), title, area, status: 'open', priority: 'normal', due: date, scheduled: date,
      summary: null, research: 'complete', ...extra,
      path: `areas/${area}/tasks/${today}-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40)}.md`,
    }
  }
  const tasks = [
    T('Approve the holiday gift box dieline with the printer', 'work', 0, {
      priority: 'high',
      summary: 'Final dieline from Pressworks needs sign-off today so boxes ship by November 20.',
      body: `
## Current state

Pressworks sent revision 3 of the dieline on Friday. The window cut-out is now 4 mm narrower, which fixes the tab collision. Waiting only on Maya's approval.

## Notes

- Box holds 4 tins (100 g each) and the tasting card.
- Printer needs approval by **5 PM today** to keep the November 20 ship date.
- Proof link: https://example.com/pressworks/proof-r3

## Subtasks

- [x] Check tin fit against the physical sample
- [x] Confirm the barcode placement with the warehouse
- [ ] Approve revision 3 in the Pressworks portal
- [ ] Send the approved PDF to the fulfillment team

## Log

- ${d(-3)}: Created from Slack (#packaging).
- ${d(-1)}: Revision 3 received.

<!-- task-research-dossier:start -->
## Research

Pressworks' standard lead time for rigid boxes is 9 business days after approval. Approving later than today pushes delivery past November 20.

Sources: Pressworks lead-time sheet; Slack thread in #packaging.
<!-- task-research-dossier:end -->

<!-- discovery-dossier:start dos-demo1 -->
## Discovery: Slack #packaging

**Current understanding:** Pressworks sent revision 3 of the holiday tin proof and needs approval to hold the November print slot.

**Next action:** Approve revision 3 in the portal, then send the approved PDF to fulfillment.

Sources: Slack #packaging thread (3 messages).
<!-- discovery-dossier:end dos-demo1 -->
`,
    }),
    T('Answer "when is it back?" for the Winter Spice Chai', 'work', 5, {
      priority: 'high',
      summary: "Customers keep asking when the Winter Spice Chai is back. Show the December 2 date on the page, collect Notify me signups and email them when it lands.",
      body: `
## Notes

Jordan in #support: "Also, can we get back-in-stock alerts on the Winter Spice Chai? We've had 30+ 'when is it back?' emails this week."

## From discovery (${d(-1)})

- Supplier confirmed 400 tins of Winter Spice Chai arrive December 2.

## Log

- ${d(-2)}: Created from discovery (Slack #support, Monday standup transcript).
- ${d(-1)}: Updated from discovery: restock date from the supplier email.
- ${d(-1)}: Research complete.

<!-- task-research-dossier:start -->
## Research dossier

**Content revision:** \`sha256:2f97b81fef29836829203751576d43e5e955dbbb76351368964b458377973bb8\`

*Researched ${d(-1)}.*

**Can Hermes do this?** Hermes needs decisions or information from you before it can finish.

### Recommended approach

- Show "Back December 2" on the Winter Spice Chai page, with a "Notify me" button on the sold-out tin.
- Use Klaviyo's back-in-stock flow, since Klaviyo already sends your email. It needs no new app or subscription.
- Email everyone who signed up when the 400 tins arrive, using your existing brand template.
- Give the support team a saved reply with the December 2 date, so they can answer the emails already waiting.
- Test the button and the alert on a sold-out test product before you publish.

### Useful context

- Jordan reports 30+ "when is it back?" emails this week in #support.
- At Monday's standup you said you'd set this up before the restock.
- The supplier confirmed 400 tins arrive December 2.
- You connected Klaviyo and built the welcome flow in a past session on October 14.
- The product template lives in the lumen-leaf-theme repo: sections/main-product.liquid.

### Dependencies and risks

- Preorders would capture sales now, but if the shipment slips, customers have already paid.
- If the supplier date moves, update the page message and the saved reply the same day.

### Open questions

- Do you want to take preorders, or only collect "Notify me" signups?
- Approve the alert email copy before it goes live.

### Access plan

- ✅ **Klaviyo** (available): Klaviyo MCP server
- ✅ **Theme code** (available): ~/code/lumen-leaf-theme
- ⛔ **Permission to edit the theme** (missing): Shopify Admin API is connected, but its token lacks write_themes. To set up: In Shopify admin, add the write_themes permission to the Hermes app
- ❔ **Shopify admin** (unverified): logged-in browser profile. To set up: Sign in once in the Lumen & Leaf browser profile

### Established approaches

- \`shopify-theme\`
- \`klaviyo-flows\`

### Sources

- [Klaviyo Help Center: back in stock](https://help.klaviyo.com/) - Setting up back-in-stock signups and the alert flow
- [Shopify Help Center: preorders](https://help.shopify.com/) - Preorder options and their payment tradeoffs
- [Shopify theme docs](https://shopify.dev/docs/storefronts/themes) - Where to add the button in the product template
<!-- task-research-dossier:end -->
`,
    }),
    T('Reply to Northwind Grocers about Q1 wholesale pricing', 'work', 0, { summary: 'Their buyer asked for the Q1 price sheet and case-pack minimums.' }),
    T('Review November ad spend against plan', 'work', 0, { research: 'running' }),
    T('Book the photographer for the spring lookbook', 'studio', 0),
    T('Pick up dry cleaning', 'home', 0, { status: 'done', completed: today }),
    T('Send updated shipping rates to the 3PL', 'work', -1, { priority: 'urgent' }),
    T('Renew the trademark filing for Lumen & Leaf', 'work', -4, { priority: 'high', due: d(2), scheduled: d(-4) }),
    T('Fix the broken link in the welcome email', 'work', -2),
    T('Call the plumber about the kitchen sink', 'home', -6),
    T('Draft the January newsletter outline', 'work', 1),
    T('Prepare the wholesale catalog for the trade show', 'work', 1, { priority: 'high', summary: 'Catalog must be at the printer by Friday for the Winter Fancy Food show.' }),
    T('Schedule the quarterly inventory count', 'work', 2),
    T('Review the new tin supplier quote', 'work', 2),
    T('Order more kraft mailers', 'studio', 2),
    T('Dentist appointment', 'home', 3),
    T('Launch the holiday bundle page', 'work', 3, {
      priority: 'high', summary: 'Bundle page with the three gift sets, live before the Black Friday email.',
      body: `
## Notes

Three bundles: Starter, Classic and Collector. Use the new lifestyle photos.

## Plan

| Phase | Time | What |
|---|---|---|
| Copy | 1h | Bundle descriptions and FAQ |
| Build | 2h | Page in the theme editor |
| QA | 30m | Mobile and checkout test |

## Subtasks

- [x] Write bundle descriptions
- [ ] Build the page
- [ ] Test checkout with a discount code

## Log

- ${d(-5)}: Created.
`,
    }),
    T('Test the discount code for the Black Friday email', 'work', 3),
    T('Write the product care card copy', 'studio', 4),
    T('Plan the team offsite agenda', 'work', 6),
    T('File monthly sales tax', 'work', 8, { priority: 'high' }),
    T('Return the library books', 'home', 5),
    T('Update the wholesale terms PDF', 'work', 9),
    T('Interview candidates for the fulfillment lead', 'work', 10),
    T('Clean up the product photo archive', 'studio', 12),
    T('Plan Thanksgiving dinner menu', 'home', 11),
    T('Quarterly review with the bookkeeper', 'work', 15),
    T('Send thank-you notes to the market vendors', 'studio', -9, { status: 'done', completed: d(-8) }),
    T('Swap the homepage hero for winter', 'work', -1, { status: 'done', completed: d(-1) }),
    T('Reconcile October payouts', 'work', -3, { status: 'done', completed: d(-3) }),
    T('Brief the designer on the spring labels', 'studio', 7, { status: 'waiting' }),
  ]
  for (const t of tasks) {
    if (!t.body) {
      t.body = `\n## Notes\n\n${t.summary || 'Captured from chat.'}\n\n## Log\n\n- ${d(-2)}: Created.\n`
    }
  }
  const byTitle = (s) => tasks.find((t) => t.title.startsWith(s))
  const bundle = byTitle('Launch the holiday bundle')
  const catalog = byTitle('Prepare the wholesale catalog')
  const newsletter = byTitle('Draft the January newsletter')
  const chai = byTitle('Answer "when is it back?"')
  const target = (t) => ({ task_id: t.task_id, title: t.title, area: t.area, due: t.due, scheduled: t.scheduled, status: t.status, path: t.path })

  const runs = [
    {
      run_id: 'run-work-today', stream: 'work', day: today, time: `${today}T12:02:00Z`, status: 'complete', mode: 'production',
      timezone: 'America/New_York', degraded: false,
      coverage: [{ source_key: 'Gmail inbox', status: 'complete' }, { source_key: 'Slack #ops', status: 'complete' }, { source_key: 'Slack #marketing', status: 'complete' }, { source_key: 'Slack #support', status: 'complete' }],
      proposals: [
        {
          proposal_id: 'p_new1', unit_id: 'u1', ref: 'A1', number: 1, kind: 'new', day: today, expires: d(7), state: 'pending', expired: false,
          title: 'Send Q1 wholesale price sheet to Harbor Market',
          current_understanding: 'Harbor Market’s buyer asked twice for the Q1 price sheet and case-pack minimums. Their order window closes next Thursday.',
          substantive_next_action: 'Export the Q1 price sheet, add the case-pack column, and reply in the same email thread.',
          source_links: ['https://mail.google.com/mail/u/0/#inbox/demo1'], research_disposition: 'confident', targets: [],
        },
        {
          proposal_id: 'p_sem1', unit_id: 'u2', ref: 'A2', number: 2, kind: 'semantic', day: today, expires: d(7), state: 'pending', expired: false,
          title: 'Add the Collector set photos to the holiday bundle page',
          current_understanding: 'Design shared the final Collector set photos in #marketing this morning, with a note that the bundle page still shows placeholders.',
          substantive_next_action: 'Swap the placeholder images on the Collector bundle and check the mobile crop.',
          new_information: ['Final Collector set photos are ready in the shared drive', 'Mobile crop should center on the tin, not the card'],
          source_links: ['https://example.slack.com/archives/C0MARKETING/p1'], research_disposition: 'confident',
          targets: [target(bundle)],
        },
        {
          proposal_id: 'p_sel1', unit_id: 'u3', ref: 'A3', number: 3, kind: 'selection', day: today, expires: d(7), state: 'pending', expired: false,
          title: 'Use the new tasting notes copy in print and email',
          current_understanding: 'The copywriter delivered tasting notes for all twelve teas. They belong in the trade show catalog and the January newsletter.',
          substantive_next_action: 'Paste the tasting notes into the catalog draft and the newsletter outline.',
          new_information: ['Tasting notes for all twelve teas are final'],
          source_links: ['https://example.slack.com/archives/C0OPS/p2'], research_disposition: 'confident',
          targets: [target(catalog), target(newsletter)],
        },
        {
          proposal_id: 'p_new2', unit_id: 'u4', ref: 'A4', number: 4, kind: 'new', day: today, expires: d(7), state: 'pending', expired: false,
          title: 'Decide whether to join the spring pop-up market',
          current_understanding: 'An organizer invited the brand to a three-day spring pop-up. The booth fee and dates are in the email; it overlaps the planned restock week.',
          substantive_next_action: 'Compare the booth fee with last year’s market sales and reply yes or no by Friday.',
          research_disposition: 'uncertain', uncertainty: ['Hermes could not find last year’s market sales, so the payoff is unclear.'],
          source_links: ['https://mail.google.com/mail/u/0/#inbox/demo2'], targets: [],
        },
      ],
      outcomes: [
        { unit_id: 'u5', title: 'Send updated shipping rates to the 3PL', task_id: byTitle('Send updated shipping').task_id, status: 'complete' },
        { unit_id: 'u6', title: 'Review the new tin supplier quote', task_id: byTitle('Review the new tin').task_id, status: 'complete' },
      ],
      conflicts: [], failures: [], delivery: { state: 'host_pending' },
    },
    {
      run_id: 'run-home-yesterday', stream: 'home', day: d(-1), time: `${d(-1)}T23:00:00Z`, status: 'complete', mode: 'production',
      timezone: 'America/New_York', degraded: true,
      coverage: [{ source_key: 'Personal email', status: 'complete' }, { source_key: 'Family calendar', status: 'failed' }],
      proposals: [
        {
          proposal_id: 'p_home1', unit_id: 'h1', ref: 'B1', number: 1, kind: 'new', day: d(-1), expires: d(6), state: 'pending', expired: false,
          title: 'Renew the car registration', area: 'home',
          current_understanding: 'The registration renewal notice arrived; it expires at the end of the month.',
          substantive_next_action: 'Renew online with the notice PIN.', source_links: ['https://mail.google.com/mail/u/0/#inbox/demo3'], targets: [],
        },
        {
          proposal_id: 'p_home2', unit_id: 'h2', ref: 'B2', number: 2, kind: 'new', day: d(-1), expires: d(6), state: 'dismissed', expired: false,
          title: 'Unsubscribe from the furniture store newsletter', targets: [],
        },
      ],
      outcomes: [], conflicts: [],
      failures: [{ title: 'Family calendar', reason: 'The calendar could not be read, so events from it were not checked.' }],
      delivery: { state: 'host_pending' },
    },
    {
      run_id: 'run-work-yesterday', stream: 'work', day: d(-1), time: `${d(-1)}T12:01:00Z`, status: 'complete', mode: 'production',
      timezone: 'America/New_York', degraded: false,
      coverage: [{ source_key: 'Gmail inbox', status: 'complete' }, { source_key: 'Slack #ops', status: 'complete' }, { source_key: 'Slack #marketing', status: 'complete' }, { source_key: 'Slack #support', status: 'complete' }],
      proposals: [
        { proposal_id: 'p_old1', unit_id: 'o1', ref: 'A1', number: 1, kind: 'new', day: d(-1), expires: d(6), state: 'complete', expired: false,
          title: 'Fix the broken link in the welcome email', targets: [],
          result: { task_id: byTitle('Fix the broken link').task_id, title: 'Fix the broken link in the welcome email', operation: 'created', state: 'complete' } },
        { proposal_id: 'p_chai2', unit_id: 'o2', ref: 'A2', number: 2, kind: 'semantic', day: d(-1), expires: d(6), state: 'complete', expired: false,
          title: 'Winter Spice Chai restock arrives December 2',
          current_understanding: 'The supplier confirmed 400 tins of Winter Spice Chai arrive December 2.',
          new_information: ['400 tins arrive December 2'],
          source_links: ['https://mail.google.com/mail/u/0/#inbox/demo-supplier'], targets: [target(chai)],
          result: { task_id: chai.task_id, title: chai.title, operation: 'updated', state: 'complete' } },
      ],
      outcomes: [], conflicts: [], failures: [], delivery: { state: 'host_pending' },
    },
    {
      run_id: 'run-work-2days', stream: 'work', day: d(-2), time: `${d(-2)}T12:01:00Z`, status: 'complete', mode: 'production',
      timezone: 'America/New_York', degraded: false,
      coverage: [{ source_key: 'Gmail inbox', status: 'complete' }, { source_key: 'Slack #support', status: 'complete' }, { source_key: 'Zoom transcripts', status: 'complete' }],
      proposals: [
        { proposal_id: 'p_chai1', unit_id: 'c1', ref: 'A1', number: 1, kind: 'new', day: d(-2), expires: d(5), state: 'complete', expired: false,
          title: chai.title,
          current_understanding: 'Customers keep emailing support to ask when the sold-out Winter Spice Chai is back. Jordan asked for back-in-stock alerts, and you said at Monday\u2019s standup that you would set it up before the restock.',
          substantive_next_action: 'Tell customers when it is back and let them sign up to be notified.',
          source_links: ['https://example.slack.com/archives/C0SUPPORT/p3', 'https://mail.google.com/mail/u/0/#inbox/demo-standup'], targets: [],
          result: { task_id: chai.task_id, title: chai.title, operation: 'created', state: 'complete' } },
      ],
      outcomes: [], conflicts: [], failures: [], delivery: { state: 'host_pending' },
    },
  ]
  for (const r of runs) {
    const ps = r.proposals
    r.summary = {
      pending: ps.filter((p) => p.state === 'pending').length, approved: ps.filter((p) => p.state === 'approved').length,
      complete: ps.filter((p) => p.state === 'complete').length, dismissed: ps.filter((p) => p.state === 'dismissed').length,
      auto_updated: r.outcomes.length, conflicts: r.conflicts.length, failures: r.failures.length,
    }
  }
  const settings = {
    streams: [
      { name: 'work', when: 'weekdays at 7:00 AM', frequency: 'weekdays', time: '7:00 AM', timezone: 'America/New_York', areas: ['work'],
        sources: [{ name: 'Gmail inbox', type: 'email', scope: 'Inbox, last 24 hours' }, { name: 'Slack #ops', type: 'chat', scope: '#ops' }, { name: 'Slack #marketing', type: 'chat', scope: '#marketing' }, { name: 'Slack #support', type: 'chat', scope: '#support' }, { name: 'Zoom transcripts', type: 'transcript', scope: 'Emailed after meetings' }],
        last_run: `${today}T12:02:00Z`, activation_state: 'active' },
      { name: 'home', when: 'daily at 6:00 PM', frequency: 'daily', time: '6:00 PM', timezone: 'America/New_York', areas: ['home'],
        sources: [{ name: 'Personal email', type: 'email', scope: 'Inbox' }, { name: 'Family calendar', type: 'other', scope: 'Next 14 days' }],
        last_run: `${d(-1)}T23:00:00Z`, activation_state: 'active' },
    ],
    tasks: { default_area: 'work', research_by_default: true, timezone: 'America/New_York', workspace_root: '~/tasks', areas: ['work', 'studio', 'home'] },
    sync: { git: 'Committed and pushed', reminders: 'Not connected' },
  }
  return { tasks, runs, settings, areas: ['work', 'studio', 'home'] }
}
