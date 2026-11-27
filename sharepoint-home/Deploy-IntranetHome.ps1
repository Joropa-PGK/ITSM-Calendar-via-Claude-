<#
.SYNOPSIS
    Provisions an intranet home page on SharePoint Online, following the
    "SharePoint Home Page Blueprint" whiteboard.

.DESCRIPTION
    1. Creates a Communication site (Topic template), unless it already exists
    2. Optionally registers it as a hub site
    3. Adds a custom tenant theme and applies it
    4. Sets header (standard, strong emphasis), mega menu and footer
    5. Creates the top navigation and footer links
    6. Builds a new home page with four sections:
         S1  full width            : Hero
         S2  two-thirds / one-third: News | Quick links + Events
         S3  three columns         : Highlighted content | People | Viva Engage
         S4  one column, strong bg : "Get help" call to action (service portal)
    7. Publishes the page and sets it as the site home page

    Content that SharePoint only stores as complex web part JSON (hero tiles,
    quick-link targets, people, Viva Engage community) is added with default
    settings and finished in the browser; see README.md.

.REQUIREMENTS
    - PowerShell 7.4+ and PnP.PowerShell 2.12+ / 3.x
        Install-Module PnP.PowerShell -Scope CurrentUser
    - Your own Entra ID app registration for PnP (one-off):
        Register-PnPEntraIDAppForInteractiveLogin -ApplicationName "PnP Intranet Provisioning" `
            -Tenant <tenant>.onmicrosoft.com -Interactive
    - SharePoint Administrator role (site creation, tenant theme, hub registration)

.EXAMPLE
    ./Deploy-IntranetHome.ps1 -TenantName contoso -ClientId 00000000-0000-0000-0000-000000000000 `
        -ServicePortalUrl "https://contoso.service-now.com/sp" -RegisterHub
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $TenantName,          # "contoso" for contoso.sharepoint.com
    [Parameter(Mandatory)] [string] $ClientId,            # PnP app registration (Application ID)
    [string] $SiteAlias        = "intranet",
    [string] $SiteTitle        = "Intranet",
    [string] $SiteDescription  = "News, services and help for all staff",
    [int]    $Lcid             = 1033,                    # 1033 English, 1031 German
    [string] $ServicePortalUrl = "https://example.service-now.com/sp",
    [string] $ThemeName        = "Corporate Intranet",
    [string] $LogoPath,                                   # optional local PNG/SVG
    [string] $PageName         = "Intranet-Home",
    [switch] $RegisterHub
)

$ErrorActionPreference = "Stop"
$adminUrl = "https://$TenantName-admin.sharepoint.com"
$siteUrl  = "https://$TenantName.sharepoint.com/sites/$SiteAlias"

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }

# Adds a web part but keeps going if a type or property is not supported by
# the installed PnP version; anything skipped is listed at the end.
$skipped = [System.Collections.Generic.List[string]]::new()
function Add-WebPartSafe {
    param($Page, [string]$Type, [int]$Section, [int]$Column, [int]$Order = 1, [hashtable]$Properties)
    try {
        $wpArgs = @{ Page = $Page; DefaultWebPartType = $Type; Section = $Section; Column = $Column; Order = $Order }
        if ($Properties) { $wpArgs.WebPartProperties = $Properties }
        Add-PnPPageWebPart @wpArgs | Out-Null
        Write-Host "    + $Type (section $Section, column $Column)"
    } catch {
        Write-Warning "    Could not add $Type in section $Section/$Column : $($_.Exception.Message)"
        $skipped.Add("$Type (section $Section, column $Column)")
    }
}

# ---------------------------------------------------------------- 1. Site
Write-Step "Connecting to SharePoint admin centre"
Connect-PnPOnline -Url $adminUrl -Interactive -ClientId $ClientId

Write-Step "Creating communication site $siteUrl (Topic template)"
$existing = Get-PnPTenantSite -Identity $siteUrl -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "    Site already exists, reusing it."
} else {
    New-PnPSite -Type CommunicationSite -Title $SiteTitle -Url $siteUrl `
        -Description $SiteDescription -SiteDesign Topic -Lcid $Lcid -Wait | Out-Null
    Write-Host "    Site created."
}

# ---------------------------------------------------------------- 2. Hub
if ($RegisterHub) {
    Write-Step "Registering site as hub"
    try { Register-PnPHubSite -Site $siteUrl | Out-Null; Write-Host "    Registered." }
    catch { Write-Warning "    Hub registration skipped: $($_.Exception.Message)" }
}

# ---------------------------------------------------------------- 3. Theme
# Primary #0A3658 (dark blue), accent #1AB7EA (cyan). Edit to match your brand.
Write-Step "Adding tenant theme '$ThemeName'"
$palette = @{
    themePrimary         = "#0a3658"; themeLighterAlt  = "#eef4f9"; themeLighter   = "#c9dbea"
    themeLight           = "#a1bfd8"; themeTertiary    = "#5689b1"; themeSecondary = "#1d5585"
    themeDarkAlt         = "#09314f"; themeDark        = "#082943"; themeDarker    = "#061e31"
    neutralLighterAlt    = "#faf9f8"; neutralLighter   = "#f3f2f1"; neutralLight   = "#edebe9"
    neutralQuaternaryAlt = "#e1dfdd"; neutralQuaternary = "#d0d0d0"; neutralTertiaryAlt = "#c8c6c4"
    neutralTertiary      = "#a19f9d"; neutralSecondary = "#605e5c"; neutralPrimaryAlt = "#3b3a39"
    neutralPrimary       = "#323130"; neutralDark      = "#201f1e"
    black                = "#000000"; white            = "#ffffff"; accent         = "#1ab7ea"
}
Add-PnPTenantTheme -Identity $ThemeName -Palette $palette -IsInverted $false -Overwrite

# ---------------------------------------------------------------- Site-level settings
Write-Step "Connecting to $siteUrl"
Connect-PnPOnline -Url $siteUrl -Interactive -ClientId $ClientId

Write-Step "Applying theme, header, mega menu"
Set-PnPWebTheme -Theme $ThemeName -WebUrl $siteUrl
Set-PnPWeb -HeaderLayout Standard -HeaderEmphasis Strong -MegaMenuEnabled:$true
if ($LogoPath) { Set-PnPSite -LogoFilePath $LogoPath }

# ---------------------------------------------------------------- 5. Navigation
Write-Step "Building top navigation (max 7 items)"
Get-PnPNavigationNode -Location TopNavigationBar | ForEach-Object {
    Remove-PnPNavigationNode -Identity $_.Id -Force
}
$nav = [ordered]@{
    "About us"  = "$siteUrl/SitePages/About-us.aspx"
    "Services"  = "$siteUrl/SitePages/Services.aspx"
    "Projects"  = "$siteUrl/SitePages/Projects.aspx"
    "Knowledge" = "$siteUrl/SitePages/Knowledge.aspx"
    "Policies"  = "$siteUrl/Shared%20Documents"
    "Get help"  = $ServicePortalUrl
    "Contact"   = "$siteUrl/SitePages/Contact.aspx"
}
foreach ($k in $nav.Keys) {
    Add-PnPNavigationNode -Location TopNavigationBar -Title $k -Url $nav[$k] | Out-Null
}

Write-Step "Enabling footer"
Set-PnPFooter -Enabled:$true -Layout Simple -BackgroundTheme Strong -Title $SiteTitle
Get-PnPNavigationNode -Location Footer | ForEach-Object { Remove-PnPNavigationNode -Identity $_.Id -Force }
$footer = [ordered]@{
    "Contact"       = "$siteUrl/SitePages/Contact.aspx"
    "Privacy"       = "$siteUrl/SitePages/Privacy.aspx"
    "Accessibility" = "$siteUrl/SitePages/Accessibility.aspx"
    "Feedback"      = "$siteUrl/SitePages/Feedback.aspx"
}
foreach ($k in $footer.Keys) {
    Add-PnPNavigationNode -Location Footer -Title $k -Url $footer[$k] | Out-Null
}

# ---------------------------------------------------------------- 6. Home page
Write-Step "Building page $PageName.aspx"
if (Get-PnPPage -Identity $PageName -ErrorAction SilentlyContinue) {
    Remove-PnPPage -Identity $PageName -Force
}
$page = Add-PnPPage -Name $PageName -LayoutType Home -CommentsEnabled:$false

# Sections: ZoneEmphasis 0 none, 1 neutral, 2 soft, 3 strong
Add-PnPPageSection -Page $page -SectionTemplate OneColumnFullWidth -Order 1 -ZoneEmphasis 0
Add-PnPPageSection -Page $page -SectionTemplate TwoColumnLeft      -Order 2 -ZoneEmphasis 0
Add-PnPPageSection -Page $page -SectionTemplate ThreeColumn        -Order 3 -ZoneEmphasis 1
Add-PnPPageSection -Page $page -SectionTemplate OneColumn          -Order 4 -ZoneEmphasis 3

# S1 Hero
Add-WebPartSafe -Page $page -Type Hero -Section 1 -Column 1

# S2 News | Quick links + Events
Add-WebPartSafe -Page $page -Type News       -Section 2 -Column 1
Add-WebPartSafe -Page $page -Type QuickLinks -Section 2 -Column 2 -Order 1 -Properties @{ title = "Quick links" }
Add-WebPartSafe -Page $page -Type Events     -Section 2 -Column 2 -Order 2 -Properties @{ title = "Upcoming events" }

# S3 Highlighted content | People | Viva Engage
Add-WebPartSafe -Page $page -Type ContentRollup -Section 3 -Column 1 -Properties @{ title = "Latest policies & templates" }
Add-WebPartSafe -Page $page -Type People        -Section 3 -Column 2 -Properties @{ title = "Key contacts" }
Add-WebPartSafe -Page $page -Type YammerEmbed   -Section 3 -Column 3

# S4 Call to action
$cta = @"
<h2>Need help?</h2>
<p><a href="$ServicePortalUrl">Raise a ticket</a> &nbsp;·&nbsp;
<a href="$ServicePortalUrl">Request access</a> &nbsp;·&nbsp;
<a href="$ServicePortalUrl">Search the knowledge base</a></p>
"@
Add-PnPPageTextPart -Page $page -Section 4 -Column 1 -Text $cta | Out-Null
Add-WebPartSafe -Page $page -Type Button -Section 4 -Column 1 -Order 2 `
    -Properties @{ label = "Open the service portal"; linkUrl = $ServicePortalUrl; alignment = "Left" }

# ---------------------------------------------------------------- 7. Publish
Write-Step "Publishing and setting as home page"
Set-PnPPage -Identity $PageName -Publish
Set-PnPHomePage -RootFolderRelativeUrl "SitePages/$PageName.aspx"

Write-Host "`nDone: $siteUrl" -ForegroundColor Green
if ($skipped.Count) {
    Write-Warning "Add these web parts by hand in the page editor:"
    $skipped | ForEach-Object { Write-Warning "  - $_" }
}
Write-Host "Next: finish the manual steps in README.md (hero tiles, quick links, people, Viva Engage, audience targeting)."
