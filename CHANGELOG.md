# Changelog

What changed in each version of [mshsfootball.com](https://mshsfootball.com). The version live on the
site is in every page's footer. Versions are MAJOR.MINOR.PATCH: MAJOR for a change in what the site is,
MINOR for a new feature or a change in how the numbers are worked out, PATCH for a fix
([CONTRIBUTING.md](CONTRIBUTING.md#releases)).

## 1.33.0

Accessibility on the Maps pages:

- **The county pills' text reads at WCAG AA (4.5:1) in both themes.** Each pill's text is dark or
  white, whichever reads better on its color, and the color is taken a little darker or lighter where
  neither would; the share images use the same colors.
- Picking a team from a map's search box with the keyboard keeps focus in the box (it used to drop to
  the top of the page); with a tap, the phone's keyboard still closes.
- In full screen, Tab and screen readers stay on the map and the site's bars; the page behind it can't
  be reached until full screen ends.
- The statewide county map is no longer 82 stops of the Tab key before the list (the list has every
  county); a county focused there shows its name and count.
- Compare and Timeline say a pick once, for every map ("Neshoba Central: Region 2-5A in 2027 and
  2028; Region 2-6A in 2026"), instead of once per map; each map's zoom buttons are named for it ("Zoom, first
  map, 2026"); Compare's pickers are the "First map" and "Second map".
- Dots, pills and the small region links are at least 24 pixels to tap, without looking any bigger.
- The Timeline's note says a team can also be found with its search.

## 1.32.0

- **A team picked on a Maps page stays picked from view to view.** The Season, Compare and Timeline
  links now carry a team picked on the page (before, only a team in the address when the page opened
  was carried).
- **Going from the Maps to Standings or the Bracket** opens a picked team's class and region this
  season (its class on the map can differ, when it moved); with no team picked, the region last open in
  Standings in that class, as it was left (its week and season); otherwise the class.
- A link naming a school by an old name opens that school in the seasons it went by it (Walnut in
  2026), rather than the school it merged into. On a Season or Compare map, a school picked in another
  season is shown as the school or schools it was then, as the Timeline and county maps already did.
- A county's link naming a school in another county, in none of its regions, says where it is
  instead of dropping it.
- The Timeline keeps the season chosen on the Season view, so going back to it returns to that
  season.
- Full screen on a county's map stays on when going to another county.
- From a county, the Regions link keeps a picked school. The header's search on a Maps page opens a
  team's standings for this season, not the Maps season.
- Changing the season on Standings keeps the picked team when it's in the class that season.
- The Maps link in the menu, and the county pages' Season, Compare and Timeline links, now switch
  pages in place rather than reloading the site.

## 1.31.0

- **A county's map shows its regions' other schools**, those outside the county, as small dots in their
  region's shade, without names (point at one, or pick it, to see which school it is), so it's clear
  how far each region reaches.
- **Picking a school on a county's map names its region's schools only**, over the other regions'
  dimmed marks, so they stay named at any zoom; before, the other schools' names could crowd them out.

## 1.30.0

- **The front page's Maps section** (once "Region maps") shows each view of the maps: a class's map as
  before, then Compare (its regions beside the season before's), Timeline (every season's) and Counties
  (the county with the most MHSAA schools), each with its image to share and a link to it.
- A county's image to share centers its list of schools beside its map, rather than starting it at the
  top.

## 1.29.0

- **Open another county from a county's map.** Tap a county around it, off the schools, to see its
  outline, its count of schools and a button to open it (the tap alone doesn't leave the page). Under
  the map, the county's neighbors are listed with their outlines, to open with one tap.
- **The Timeline's Older and Newer buttons** step through the seasons a season at a time when they
  don't all fit on screen, beside its search box (on a phone, under it).

## 1.28.0

- The front page's links to the maps now read **Maps**, as the menu does.
- On the Counties map, the county you point at or tab to is outlined whole, on top of its neighbors;
  before, the counties drawn after it covered part of its edge. Its search box reads "Find a county on
  the map", and each county it finds shows the county's outline, shaded as on the map.
- In full screen, a county's map turns the header's search into a county search (on a Regions map it
  already finds the map's teams).
- A school picked on one of a county's Timeline maps is picked on every season's map, and those it
  isn't on say where it was, as Compare's two maps do. A link to a county's Timeline can name a school
  (?team=), as one to its Compare can.
- On a county's Compare, each map's count of schools lines up with its season picker.
- Picking from a dropdown on a Compare page (or anywhere the page redraws) by tap or click no longer
  leaves the dropdown focused; on phones, that opened it again. With the keyboard, focus stays on it.

## 1.27.0

- **Share on the Counties pages.** A county's page shares its map and schools by class, and the county
  against the regions before; its Compare shares the two seasons together when they're back to back,
  and each map's own; its Timeline, every season on one image. The statewide page shares every
  county shaded by its MHSAA schools. Each image has the county's outline as its mark.
- Links to the Counties pages show their own previews: the county's map, or every county shaded.
- **A county's map puts class first.** Each of its schools is marked with its region and class (3-6A),
  in its class's color (7A blue, 6A green, 5A orange, 4A purple, 3A yellow, 2A pink, 1A red), lighter
  or darker for its different regions. Every school in the county is named; schools elsewhere in its
  regions are no longer drawn (the regions' shapes still are, lighter, a picked school's in full).
  Marks that would overlap are spread apart, a line back to each school's spot, until you zoom in;
  picking a school keeps the map on the county. The list and the season-by-season table show the
  same marks.

## 1.26.0

- **A county's Compare and Timeline**, as the Regions pages have. Compare shows the county in two
  seasons side by side (each with its own season) and what changed: its schools that changed class
  or region, those new to it, and those gone. A merged school says what it was formed from (Leake in
  2026: Leake Central and Leake County). Pick a school on either map, or in the list, to see it on
  both.
- The Timeline shows the county's map every season, oldest first, and a table of its schools season
  by season, each season's region in that map's colors. A merger is said on both ends ("Part of
  North Tippah from 2027"; "From Walnut and Falkner, 2027").

## 1.25.0

- **Counties, a new kind of map.** Pick "Counties" beside the classes (on a phone, the Regions |
  Counties switch above them) to see every county shaded by how many MHSAA schools it has. Pick one,
  on the map, in the list or by name, to see its schools whatever their classes, each with its
  region: the county outlined, each school's region in its own color (two regions with the same
  number in different classes never share one), and the regions' other schools as smaller dots.
  A school's county is the one its campus is in.
- Each county has its outline as its mark, as a team has its helmet: beside its name on its page,
  and in the list of every county, shaded as on the map.
- Only MHSAA schools are counted or shown, and the pages say so.
- The Counties pages read without JavaScript too, and are in the sitemap.

## 1.24.0

- **Share on Compare and on the Timeline shares what you're looking at.** Before, both offered the
  Season view's images. When Compare's maps are back-to-back seasons, it offers them side by side: the
  class's (when both maps show one class) and a followed team's (when it was in a region both
  seasons). It always offers each map's own image too, shared with the page's link.
- **The Timeline has images to share**: a class's regions over every season, or a followed team's,
  all on one image, with a small map for each season. However many seasons there are, it's one image;
  more seasons make it taller. A school's seasons before a consolidation show each school merged into
  it, each in its own region (North Tippah's 2025 and 2026: Walnut and Falkner).
- On a phone, the Timeline page could be dragged sideways past its edge. It stays put now.

## 1.23.1

- **Share images' titles use the site's title font (Nippo).** Since 1.17.0, deploys run images built
  from the public repository, which can't include the font, so the images' titles fell back to Inter
  Bold. The images now read the font installed on the server, and the first update after this one
  draws them all again with it.

## 1.23.0

- **The Timeline holds any number of seasons.** Each map keeps a readable width, the row scrolls
  sideways when there are more than fit, and it opens at the newest.
- **Following a team on the Timeline shows its seasons in a table** under the maps: its region each
  season and the region's other schools.
- **A consolidated school's history goes back through the schools merged into it.** Follow North
  Tippah and 2025 and 2026 show Walnut and Falkner, each with its region; follow Leake and 2025 shows
  Leake Central and Leake County.
- On Compare, the class picker at the top sets both maps' class (a map's own picker still sets just
  that map's).

## 1.22.0

- **Zoom in on a map and the schools are named.** A name sits right beside its dot only where that
  dot is plainly the nearest one, so it can't be taken for a neighbor's; otherwise it sits a little
  farther out with a line to its dot. Names cover no dot or other name, the picked team's region gets
  first pick, and the other regions' names are dimmed. Names with no room wait until you zoom in.
- **Pointing at a dot shows more**: the school's helmet, name and mascot, its region and town, and the
  seasons the map is of, edged in its color.
- A region's number sits in the middle of its small circle again (under the map and in the tooltip, it
  sat a little low).

## 1.21.0

- **On the Maps, a picked team is followed everywhere.** Pick a team, on a map or with the search, and
  each map shows the class it was in that season: the Season view switches to it, both of Compare's
  maps follow it, and so does every map of the Timeline. It stays picked as you move between Season,
  Compare and Timeline. A map of a season it wasn't in a region says so.
- Choosing a class yourself (the class picker, or a Compare map's class) keeps the team only if it's
  in that class there; otherwise it shows the class you chose, and the other map stays as it was.
  An empty spot on a map stops following.
- **Full screen stays on when you change the class or season**, and while it's on, the search at the
  top finds teams on the map.
- On Compare, changing the second map's season or class no longer jumps to the first map's.

## 1.20.0

- **A Timeline of a class's regions.** Every map page has a third view, Timeline: a map for each season
  of regions, oldest first (2025, 2026, and 2027 and 2028 so far). Pick a team on any map, or with
  "Follow a team", to follow it through every season: each map shows its class and region that season,
  and its region's other schools, so you can see who it has shared a region with over the years. On a
  phone, swipe from one season to the next.

## 1.19.0

- **Compare two region maps side by side.** Every map page now has two views, Season and Compare. Compare
  shows two maps, each with its own season and class (at first, the same class's regions before
  these), and pick a team on either one to see where it is on both. Under them, what changed: the
  schools that moved into and out of the class (and which way), the ones that changed region, and
  the ones that stayed put.

## 1.18.0

- **Regions is now Maps.** The nav's "Regions" is now "Maps", the home of the site's maps, starting
  with the region maps, now at `/maps/regions/5a`. Links to the old addresses (`/regions/5a`, with
  any team or season in them) still work: they go to the new one.

## 1.17.7

- **The Regions page's full screen keeps the site's header and the class picker's bar**, which says
  what's on screen (such as "Class 1A Regions · 2027 and 2028 seasons"). The map fills the space
  under them.
- **Full screen is no longer offered on a phone**, where it showed the state no bigger than the page
  already does. On a tablet, it still stops above the tab bar along the bottom.
- **On a phone, the map and its buttons fit between the header and the tab bar**, so the buttons no
  longer hide under the tab bar, and the map no longer changes size as you scroll (as the address bar
  comes and goes).
- **The map can't be dragged away from Mississippi**: it stops while part of the state is still in view.

## 1.17.6

- **The Regions page's map fits in one view.** Once you scroll down to it, the whole state, the map's
  buttons and a picked team's details all show at once, and the map stays in view as you scroll the
  lists. On a phone it's as big as the screen allows.
- **Full screen.** The map's new "Full screen" button shows it over the whole page, with the picked
  team under it; "Exit full screen" or Escape brings the page back. The buttons are now under the
  map, so they never cover a school, and "Show the whole state" is a reset arrow.
- **The lists read as teams, not links.** A team is a row you pick to see it on the map; the one you
  picked is tinted in its region's color. A region with standings has its own "2026 standings" link
  beside its name, so it's clear which goes where.
- **The map has room around the state**, and a region's shape is no longer cut off at the state
  line or the coast, so a school on the coast or the state line sits inside its region's shape like
  every other school. The share images draw the same shapes.
- **County lines show over every region's color**, in light and dark mode, on the page and in the
  share images.
- **A picked team's details are easier to read**: its helmet, name and region, where it is, and the
  region's other schools, each of which you can pick in turn.
- Picking another team in the same region no longer zooms the map again.
- A team's name, when you point at its dot, stays inside the map, and shows under the dot near the top.

## 1.17.5

- **Aberdeen stays in 2A Region 4 in 2027 and 2028.** Its appeal to move to Region 1 was rescinded,
  so the Regions page no longer shows it moving.

## 1.17.4

- **A team's expanded row on a region page reads in order.** At the top: its record and Elo rating,
  with its share button. Below, from left to right: its region games (completed, then remaining),
  its seeding odds, and its playoff path. Every heading is in the site's heading type.
- Its odds are all the same width, so a "100%" no longer sticks out past the others, and a playoff
  round's name stays on one line, so the rows of the playoff path are evenly spaced.
- The playoff path's middle column is now "Hosts, if they get there".
- **"Share this region" can share a team too.** Its first choice is the region or any of its teams,
  the same images as a team's own share button.

## 1.17.3

- **The 2027 and 2028 regions include the MHSAA's approved appeals.** On the Regions page:
  - 4A: Choctaw Central moves from Region 3 to Region 5, and Columbia from Region 6 to Region 7.
  - 3A: Jefferson Davis County moves from Region 7 to Region 8.
  - 2A: Wesson moves from Region 6 to Region 7, and Aberdeen from Region 4 to Region 1.

## 1.17.2

- **The bar under the header fits on a phone.** Once you scroll down a page, the bar under the
  header says what's on screen, such as "Class 2A · Second Round · Nov 13 · Projected". On a phone it
  was cut off to one line, which could hide which odds the page shows. It now takes a second line
  when it needs one, without the bar getting any taller.
- Opening the class picker from that bar no longer moves its button to the other side of the
  screen: the button stays where it is, and the classes open under it.

## 1.17.1

- **A score after a first-round bye shows on the bracket.** In 1A, Region 1 has three teams, so the
  Region 3 #1 seed, Calhoun City, had a bye in the first round. The bracket didn't carry Calhoun
  City past the bye, so its second-round game against French Camp showed no score: Calhoun City won
  46–28. It now shows, with Calhoun City through to the quarterfinals.

## 1.17.0

- **Share images for every season.** A past season's region pages now have images to share, as the
  season finished: each region's standings and playoff results, and each team's season, like the
  past seasons' brackets already did. The Regions page's older seasons (2026, 2025) now have their
  maps to share too; before, their Share button opened a sheet with a broken image. The rule is the
  same everywhere: there's a Share button on a season's latest update, and its images match the page.
- Images the site no longer uses (a season it no longer has, a region gone in a realignment) are now
  removed after each update, so they don't build up.

## 1.16.4

- **The Regions page's visit counts.** The site now also counts the first time someone moves or
  zooms a region map on a page, opens a region's standings from the region maps, and whether a team
  was picked on the map or in the lists. The About page's "What visitor metrics we capture" lists
  these, and now also the sharing that was already counted: opening a share sheet, and sharing,
  downloading or copying the link to an image.
- Picking a team in the Regions page's lists no longer reloads the page or adds a step to the back
  button; it picks the team in place, as picking its dot on the map does.

## 1.16.3

- **Two games show their real opponent.** Amanda Elzy's Aug 28, 2026 game was against Charleston,
  and Bay Springs' Sep 12, 2025 game against Forest Hill; each school's AHSFHS page named another
  team. The team ratings had counted each as a second game, against a team that played someone else
  that night. The 2026 numbers are worked out again with the game counted once; the 2025 season's
  stored numbers are left as they were.
- **A canceled game has no score.** West Tallahatchie vs Ashland on Sep 25, 2026 wasn't played, though
  West Tallahatchie's page listed a 1–0 win. It now shows as canceled and counts for neither team.
  A canceled region game also no longer counts as a game left to play in the odds.

## 1.16.2

- **A game's score shows for both teams once either team's page has it.** Scores come from
  each school's own page on AHSFHS, and the two pages don't always update together. Until now, a
  game final on one school's page still counted as unplayed for the other school: no score on its
  schedule and missing from its record, and for a region game, counted for one team but not the
  other in the region's standings. Now both teams get the score.
- When the two schools' pages both have a game final but with different scores, neither score
  counts until they match or a correction is approved: the game shows no score and counts as
  unplayed, rather than counting differently for each team.

## 1.16.1

- **Playoff odds use the same team ratings as the rest of the season.** Once a class's playoffs
  start, its odds of reaching each round and of hosting are worked out again after each round. That
  work started every team at its class's starting rating, ignoring how it finished last season,
  while the odds before the playoffs carried last season's ratings over. Now both do.
- Behind the scenes, the morning update does less work: a region whose games and ratings haven't
  changed since the last update keeps its odds and scenarios instead of working them out again, and
  a link preview or bracket image is drawn again only when what it shows, or how it's drawn, has
  changed.

## 1.16.0

- **The class buttons stay in reach.** On Standings, Bracket and Regions pages the 1A–7A buttons are
  pinned under the header as you scroll, so you can switch classes from anywhere on the page. Once
  the page's title scrolls away, the same bar also says what's on screen ("Region 2-5A · Week 11 ·
  Nov 5 · Projected"). On phones the bar folds to that line and a "5A" button that opens the classes.
- The Regions page now shows that line too ("Class 5A Regions · 2027 and 2028 seasons").

## 1.15.0

- **A class's regions, then and now.** A new image to share puts a class's 2026 regions beside its
  2027 regions, with the schools that left the class ("Now 3-4A") and those new to it ("From 4-4A").
- **Region maps on the front page.** A "Region maps" section shows a class's map and links to its
  Regions page, and the class buttons under the helmet have a Region Maps row.
- **The Regions page's lists** show each team's helmet, run two regions across on wider screens, and say where a team
  was the season before only when it was in a different region.
- **The map's search box** works like the one at the top of the page, with the same list of matches.
  The search at the top of the page now works on the Regions page too; before, it stayed on
  "Loading teams…" there. Its matches now name the region as "Region 6-3A".
- On the Regions page, the share button is beside the title, the zoom buttons are at the top left, where
  they cover less of the state, and dragging the map no longer selects it. The note on how the map is drawn moved to the
  About page ("How the region maps work").
- In the region images, team names no longer overlap on the map (a crowded one sits a little away,
  with a line to its dot), "Still in the Region" no longer repeats the region, and the
  "MHSAA 2027–29 regions" line at the bottom is gone.

## 1.14.0

- **Regions, on a map.** A new Regions tab (`/regions/5a`) shows each class's schools on a map of
  Mississippi, each a dot numbered by its region, with a shaded shape around each region's schools and
  the schools listed by region. It opens on the 2027–29 regions MHSAA released in November; a picker
  shows the 2025 and 2026 regions too. Zoom in for the county names. Pick a team (on the map, in the
  list, or by typing its name) to highlight its region and see where it was the season before ("Moved
  up from Region 4-4A"). The county lines are the Census Bureau's, and a public school's dot is at the
  federal (NCES) geocode of its address. MHSAA doesn't draw region boundaries, so the shapes are only
  drawn around each region's schools, and two regions' shapes never overlap.
- **Region maps to share.** From the Regions page: a class's map, a team's new region with its New
  Region Members, and a team's 2026 region beside its 2027 region, each in light or dark. Links to a
  Regions page or a team on it preview with its map.
- The front page, the 404 page and every page's menu link the Regions pages.

## 1.13.2

- **A finished game keeps its seeds.** On a bracket, a played game still shows each team's region and
  seed under its name ("Region 2 #2 Seed"), on the bracket, in the game's sheet, and in the bracket
  images to share. Before, the seed went away once the game was played. Past seasons' bracket images
  are drawn again once to pick this up, and from now on whenever the way they're drawn changes.
- **The About page has a table of contents**, "On this page", linking to each section.

## 1.13.1

- **Shorter hosting reasons in 5A–7A quarterfinals.** Where only the first round comes before a
  quarterfinal, opponents from different regions have always hosted the same number of playoff games,
  so "fewer home games hosts" never decides who hosts there. The reason now says just what does:
  "Brookhaven hosted as the higher seed: Region 3 #1 over Region 4 #2", not "both had played 1 home
  playoff game, so the higher seed hosts". It's worked out from each bracket, so it follows any change
  to a class's format. 1A–4A quarterfinals, where a second round comes first, still give the count.

## 1.13.0

- **Why a team hosts a playoff game.** A bracket game's sheet now says which of the MHSAA's home team
  rules picks its host: under each possible matchup whose host is settled ("Booneville hosts as the
  higher seed: Region 1 #1 over Region 4 #2"), and under the score of a game already played
  ("Okolona hosted; it had played 0 home playoff games to Biggersville’s 2, and the team with fewer
  hosts the quarterfinal"). When who hosts depends on how the teams get there, each way in the
  matchup's "How?" ends with its reason ("Noxubee County hosts; it will have played 1 home playoff
  game to Thomas E. Edwards’s 2, …").

## 1.12.1

- **Fixed: the games list left out a rematch.** A playoff game between two teams that had already met
  in the regular season (29 of 2025's playoff games, the Raleigh–Seminary semifinal among them) was
  missing from the site's list of games, which the region pages and the API use. The site's own
  pages didn't show those games there (brackets and playoff roads come from the bracket), but the
  API's list was incomplete. It now lists every game.
- **One date for a game.** When the two schools' schedules date a game a day apart, the games list
  now gives it the same date from either side: the later one, the date the standings count it on.
  Before, it gave the earlier one, so a region page looked at as of the earlier day showed the
  result while its standings didn't count it yet (Region 1-5A as of Oct 15, 2026 listed New Hope's
  41–14 win over Columbus under Completed games, with New Hope still 1–0 in the region).

## 1.12.0

- **Share what has to happen for a team.** While a region still has games left, sharing a team from
  its row on the region page also offers “What has to happen”: the outcomes the region page lists
  for that team (winning the region, a playoff spot, each seed), each with its chance and the results
  that give it, or before full scenarios, the results that settle a spot for it. A long list runs
  over several pages; one that would need more than five stops at four and says how many more
  outcomes are on the region page. The button in the team's row is now “Share Magee”, since it
  offers more than the season.

## 1.11.0

- **Share a team's season.** On a region page, a team's expanded row now has “Share Magee’s season”:
  a picture of its season to share, with its games and scores, its chance of each seed and of the
  playoffs, its region's standings with its row marked, and its road through the playoffs: each
  round's chance of getting there and of hosting, and once it's playing, its results and next game
  (the state champion gets the trophy). In Projected or Toss-up odds, light or dark. Like the
  region's images, it's of the latest update.

## 1.10.0

- **Share a region's scenarios.** The region page's share button now also offers its scenarios as
  images: every way the region can finish, with each one's chance and, where there's room, why tied
  teams finish in that order; or, before full scenarios, the results that settle a spot no matter
  what else happens. A long list runs over several pages (shared or downloaded together); one that
  would need more than five stops at four and says how many more are on the region page.

## 1.9.0

- **Share a region as an image.** A region page's new share button (at the right of its title) opens
  a picture of the region to share: its standings with each team's odds of every seed and of the
  playoffs, and its remaining games; once its games are all played, its playoff teams and how they've
  fared (the state champion gets the trophy). In Projected or Toss-up odds, light or dark, sized for a
  phone and for social feeds. Share it, download it, or copy its link, which always shows the latest
  update. Like the bracket's, it's of the latest update, so the button shows only there.

## 1.8.0

- **A bracket link shows the bracket.** Paste a link to a bracket page into a message or a post, and
  its preview is now a picture of the whole bracket, titled with its season (“2026 Class 3A
  Bracket”), with the two teams likeliest to win the state championship and their Projected chances, or once
  it's played, the state champion. A link to an earlier season's bracket shows that season's bracket.

## 1.7.2

- **Shorter “what has to happen” lists.** A list no longer repeats what an earlier way already
  covers: “Lanier beats Vicksburg, OR Provine and Florence win and Vicksburg beats Lanier” is now
  “Lanier beats Vicksburg, OR Provine and Florence win” (when Lanier wins, the first way already
  holds). The conditions mean exactly what they did. A team that's sure of a playoff spot is now
  said to have clinched one.
- **Fixed:** two identical ways in a list (the same conditions in another order) could cancel each
  other out, leaving nothing. None of today's lists came out empty.
- **Bracket “How?” panels:** when a team (or a matchup) could get to a game as more than one seed,
  the seeds are listed one after another with OR between them, without a “ONE OF” box around them
  all.

## 1.7.1

- **Clearer bracket images.** Their title now has the season: “2026 Class 3A Bracket”. Only the
  image with Projected odds keeps a line under the title (saying what the odds are and how each open
  spot is filled); the blank and finished ones no longer repeat what's plain or already in the footer.
  When you share one, the sheet says “Class 3A · as of Oct 30”, or for a past season,
  “Class 6A · 2025 season · Final”.
- **A tidier bracket page.** The share button is now just its icon, at the right of the bracket's
  title (screen readers still hear “Share this bracket”).
- **Fixed:** when the season, week and odds controls wrap onto a second line (on phones), the
  second line no longer starts indented.

## 1.7.0

- **Share a bracket as an image.** “Share this bracket”, under a bracket's controls, opens a choice of
  images: the North half, the South half or the whole bracket; with Projected odds or blank (results
  and teams that are set, no odds); light or dark. It starts on the half you're looking at, your odds
  (blank in Toss-up odds, which has no image) and your theme, and shows the image before you send it.
  Where the browser can share files (most phones), Share hands the image to any app; anywhere, you can
  download it, or copy its link, which for this season always shows the latest update. Past seasons' brackets can be shared too, blank, as they
  ended. The images are of the latest update, so the button shows only there, not on an earlier week.

## 1.6.0

- **The projected champion.** Under the Championship Game on a bracket, in Projected odds: the team
  likeliest to win the state championship and its chance, “Projected champion: Seminary · 42%”. It's
  the same chance the team's own page gives, and it's left off in Toss-up odds and once the game is
  played. The image of the whole bracket with Projected odds shows it too.
- **Each team's chance to win it all.** Opening the Championship Game lists the teams likeliest to
  win the state championship, with their chances.
- **Where the championship is played.** Where a championship game said “Neutral site”, it now names
  the venue on record for that season, such as “Davis Wade Stadium • Starkville”: under the game on the
  bracket, in its details, on the state champion's card (“in the Championship Game at Davis Wade
  Stadium in Starkville”), on the image of the whole bracket, and on a team's bracket image.

## 1.5.0

- **The state champion, with a trophy.** A finished season's bracket now opens with its champion: a
  gold football trophy modeled on the MHSAA's, then “2025 Class 3A State Champion”, the team, and the
  championship game's score. The image of the whole bracket shows the trophy over the championship
  game too. Looking at the bracket as of an earlier week, before the final, doesn't show it.

## 1.4.0

- **A playoff path reads in order.** A team's “How?” for a later playoff game now lists the
  regular-season results its seed needs first, then the playoff games it has to win. Before, the
  playoff games could come first.
- **What it takes for a later playoff matchup, and who hosts it.** Each possible matchup in a
  second-round or later game now has a “How?” too: the seeds that lead both teams there, with what
  each takes, then each playoff game they have to win. When either team could host, it's split into
  “Noxubee County hosts IF” and “Thomas E. Edwards hosts IF”, following the MHSAA's hosting rules;
  in a quarterfinal that can come down to whom a team beat in the second round, which it then names.

## 1.3.0

- **What it takes to reach any playoff game.** Every team listed in a later playoff game on a bracket
  now has a “How?” too: the seed or seeds that lead there, with what each one takes, and each playoff
  game it has to win on the way, naming the opponent once it's known. Games it has already won drop
  out, and a bye needs no win. The team you've picked opens on its own, on either side of the game.

## 1.2.0

- **What it takes to reach a first-round playoff game.** In a first-round game on a bracket, each
  team that could play there, and each possible matchup, has a “How?” that opens what has to happen:
  the same conditions the region's page lists for that seed, and for a matchup, both teams' at once.
  The team you've picked opens on its own. Until a region has five or fewer region games left, it shows the
  results that would settle the spot, if there are any, and links to the region.
- **A tidier game sheet.** Its teams and matchups are separated by lines, and “Possible matchups” is
  a section header.

## 1.1.2

- **A bye reads as a bye.** When a region has only three teams, the team that would have played its
  #4 seed in the first round gets a bye. The bracket now shows “BYE” there, and the game's sheet
  says why: “There is no Region 1 #4 Seed, so Calhoun City gets a bye.” Before, it showed “No team
  can get here” and said that so many teams could still meet there that no matchup had even a 0.5%
  chance, which wasn't true.

## 1.1.1

- **Another class keeps your week.** Switching class on the standings or a bracket stays on the season
  and week you picked: the same calendar week, under that class's name for it (2025's “Second Round”
  in 1A–4A is “First Round” in 5A–7A). If that class didn't play that week, it shows the closest
  earlier week it did. Before, it went back to the latest week.
- **Each class remembers its team.** A team you pick in a class stays picked there for the rest of
  your visit: look at other classes, and it's there again when you come back, on the class's standings
  and its bracket. A team picked in one class doesn't affect another. “Show every team”, or picking the
  team again, clears it. The class page now marks the picked team's row too. Before, switching class
  cleared the pick.

## 1.1.0

- **Report a game's final score.** A region game from today or earlier that has no score yet has a
  “Report score” button, next to the “Wrong score?” one on finished games. A moderator checks the
  score, and once it's approved, the next update of the standings, odds and scenarios counts the game
  as played for both teams.
- **Corrections reach past weeks, and quickly.** Once moderators have stopped approving corrections
  for 10 minutes, the standings, odds and scenarios are worked out again from the earliest date the
  corrections change, past weeks included. Before, a correction waited for the next morning's update,
  and past weeks kept the old numbers.
- **The morning update appears all at once.** The new scores, standings, odds and scenarios replace
  the old ones together when the whole update is done. Before, the scores showed first and each
  region's numbers as it was worked out. If the update fails partway, the site keeps the previous
  day's numbers whole.
- **Report a playoff game's final score.** On a bracket, a game whose two teams are set and that has
  no result yet has “Already played? Report the final score.” A moderator checks it, adding the game
  for both teams if the schedule doesn't have it yet.
- **Report a game's right date.** Every region game with a date has a “Wrong date?” button. Once a
  moderator approves the report, the game moves to that date for both teams.

## 1.0.2

- **Scenarios a tie's margins decide are listed one by one.** When one set of results in a region's
  last games leaves a tie the winning margins can order nine to twelve different ways, each of
  which can be put in margins, its card said only that the tiebreaker decides it. Now each order is its own card with the margins that
  give it: a range ("by 1–3") or, where it needs one, a comparison of two games' margins ("McAdams
  wins by at least 3 more points than Sebastopol"). Region 5-1A's last week is one. A card that
  named the tiebreaker steps behind its order also says the margins instead, where that's short.

## 1.0.1

- **A game the two schools' schedules date a day apart now counts once.** Some games are dated a day
  apart on the two schools' schedules (Falkner–H. W. Byers, for one). Such a game counted twice in the
  Elo ratings behind the Projected odds, and twice in the point differential and points allowed that
  the tiebreakers use. On a past week dated between the two days, it counted for one of the two
  teams and not the other. Each game now has one date, the later of the two, everywhere a date
  decides what has been played. A rematch, like a playoff game between region opponents, is still a
  game of its own.

## 1.0.0

The first public release: standings, playoff odds and scenarios for every MHSAA region in classes 1A–7A.

- **Standings and seeding odds** for every region, updated each morning from the previous night's
  scores, in two kinds: Toss-up (every remaining game a coin flip) and Projected (weighted by the
  teams' Elo ratings).
- **Scenarios** once a region has five or fewer games left: every way it can finish, what makes each
  happen, margins included, and why the tiebreaker orders each tie as it does, step by step.
- **Team paths** with ten or fewer games left: for each team, the results that give it each seed, a
  playoff spot, or elimination.
- **Key insights** with six to ten games left, where the full scenario list isn't shown: the results
  that clinch a seed or eliminate a team.
- **Playoff brackets** with each team's odds of reaching each round and of hosting.
- **Past weeks**: any game date's standings and odds as they stood then, for the 2025 and 2026 seasons.
- **Ties in finished standings** explained with the actual results.
- **Feedback and reader submissions** (score corrections, logos, helmets, colors and locations),
  reviewed before they're used.
