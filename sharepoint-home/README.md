# Intranet home page: build runbook

Builds the layout from the *SharePoint Home Page Blueprint* whiteboard on SharePoint Online.

## 1. Prerequisites (one-off, about 15 minutes)

| What | How |
|---|---|
| PowerShell 7.4+ | `winget install Microsoft.PowerShell` |
| PnP.PowerShell | `Install-Module PnP.PowerShell -Scope CurrentUser` |
| Entra ID app for PnP | `Register-PnPEntraIDAppForInteractiveLogin -ApplicationName "PnP Intranet Provisioning" -Tenant <tenant>.onmicrosoft.com -Interactive` → note the Application (client) ID |
| Role | SharePoint Administrator (site creation, tenant theme, hub) |

## 2. Run the script (about 5 minutes)

```powershell
./Deploy-IntranetHome.ps1 -TenantName contoso -ClientId <app-id> `
    -ServicePortalUrl "https://contoso.service-now.com/sp" -Lcid 1031 -RegisterHub
```

You can run it again safely: it reuses the site and rebuilds the home page.

## 3. What the script builds vs. what needs the browser

| Element | Script | Finish by hand (Edit page) |
|---|---|---|
| Communication site, Topic template, hub | ✔ | – |
| Tenant theme (primary `#0A3658`, accent `#1AB7EA`) | ✔ | Change colours in the script if needed |
| Header: standard, strong; mega menu | ✔ | Upload logo if not passed with `-LogoPath` |
| Top navigation (7 items) + footer links | ✔ | Create the target pages (About us, Services, …) |
| Section 1: Hero | ✔ placeholder | Pick 5 tiles: image, title, link |
| Section 2: News, Quick links, Events | ✔ | Add the 8 quick-link targets; check Events source list |
| Section 3: Highlighted content, People, Viva Engage | ✔ | Filter Highlighted content by metadata; add contacts; pick Engage community |
| Section 4: Get help call to action | ✔ text + button | Check links point to the right portal pages |
| Audience targeting | – | Turn on per web part (News, Quick links, navigation) |

Web parts the installed PnP version cannot add are listed at the end of the run; add those in the page editor.

## 4. Go-live checklist

- [ ] Hero has 5 tiles with real images (1200 × 675 px or larger, alt text set)
- [ ] At least 3 news posts published before launch
- [ ] Page owner and backup named in site settings
- [ ] Tested on mobile (SharePoint app) and at 100 % / 200 % zoom
- [ ] Site visitors = Everyone except external users (or your staff group)
- [ ] Set as the organisation's home site if this is the main intranet (`Set-PnPHomeSite -HomeSiteUrl <url>`, admin)
