# Giving a cloud session your X sign-in

The capture browser signs in with one cookie from a browser where you are already signed in to X:
`auth_token`. You store it yourself as an environment variable on the cloud environment; it never goes
through chat and never enters the repository.

Two facts to weigh once. X's Terms of Service (effective 9 October 2026) say "you cannot scrape the Services
without X's express written permission, try to work around any technical limitations we impose". And
`auth_token` is full access to the account it comes from, used here from a data-centre IP by an automated
browser, which is the pattern X locks accounts for. A secondary account removes that exposure from your main one.

## A. Copy the cookie (Chrome or Edge, on your computer)

1. Open `https://x.com/home`. Result: your home timeline, signed in to the account you want the capture to use.
2. Press `F12` (macOS: `Cmd`+`Option`+`I`). Result: the DevTools panel opens.
3. Click the **Application** tab in the DevTools top bar (behind `»` if the panel is narrow). Result: a left
   sidebar with a **Storage** group.
4. In that sidebar, under **Storage**, expand **Cookies** and click `https://x.com`. Result: a table of cookies.
5. Click the **Filter** box above the table and type `auth_token`. Result: one row named `auth_token`.
6. Double-click that row's **Value** cell and press `Ctrl`+`C` (macOS: `Cmd`+`C`). Result: a 40-character
   string of digits and the letters a-f is on your clipboard.

## B. Store it on the cloud environment

7. Open the Claude Code session for this repository at `https://claude.ai/code`.
8. In the session's title bar, click the cloud environment name (`Full Internet Access (take care)`).
   Result: the environment menu opens.
9. Click **Edit**. Result: the environment's settings open, with an **Environment variables** field.
10. In **Environment variables**, add a new line: `X_AUTH_TOKEN=` followed by the value from step 6, with no
    spaces or quotes. Leave the existing lines unchanged.
11. Click **Save**. Result: the settings close.

## C. Use it

12. Start a **new** session on the `X-map` repository with that same environment selected (a variable is
    read when a session starts, so the session that was open while you saved it does not have it).
13. Send: `Map @astridwilde`. Result: the first lines of the run include `signed-in session confirmed`.
    If they say `auth_failed`, the cookie was copied incompletely or that browser has since signed out:
    repeat from step 1.

## Revoking

Sign out of X in the browser you copied the cookie from: that invalidates the token everywhere. Then delete
the `X_AUTH_TOKEN` line from the environment (steps 8-11).

## Running on your own computer instead

`X_AUTH_TOKEN=<value> bin/xmap run <handle>` works the same way from a clone, using your own IP address and
a visible Chromium window. Requires Node 20+ and Playwright's Chromium (`npm i playwright && npx playwright install chromium`).
