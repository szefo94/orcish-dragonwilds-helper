# How fishing works in RS: Dragonwilds — working notes for a future bot

Sources, written in my own words:
- The official Dragonwilds wiki "Fishing" page (last edited 15 Aug 2026).
- Guides from PC Gamer, BisectHosting and Sportskeeda.

The YouTube video you linked (stYW8Bm-MGk) could not be opened from my side (rate limit). If it shows something that contradicts these notes, the video wins; edit this text.

Status markers: [WIKI] = stated by the wiki. [GUIDE] = stated by guides. [ASSUMPTION] = my inference, must be verified in game.

## 1. Unlock and gear
- [WIKI] Fishing is the 11th skill, added 21 Apr 2026 (update 0.11.1), max level 99.
- [WIKI/GUIDE] Start: craft a Coarse Net (2x Coarse Thread; flax → spinning wheel → thread), then the Wise Old Man in Bramblemead gives the "Shrimp Catcher" quest.
- [GUIDE] Rods unlock at Fishing level 3 (first: Ash Rod = Ash Log + Coarse Thread).
- [WIKI] Nets work only on NET fishing spots; rods only on ROD fishing spots.
- [GUIDE] All spots appear as white rippling circles in the water. Rod spots are the larger ripples.
- [WIKI] Region gear: Brynmoor → Ash Rod, Ghornfell → Oak, Fellhollow → Willow, Dowdun Reach → Maple, Umbral Sands → Yew. Each fish type has a matching bait.

## 2. Net fishing (simple loop — the easiest thing to automate)
- [WIKI] Stand near a net spot with a net equipped and use the Trawl action (default LMB).
- [WIKI] Each trawl costs 10 stamina.
- [WIKI] It only works in range of a non-depleted spot. A depleted spot gives a "no fish here" notification.
- [WIKI] Catches can be fish or junk (stone, weeds). From level 49 the catch chance is 75%.
- [ASSUMPTION] So the loop is: trawl → wait for the animation/result → repeat while stamina lasts → wait for stamina to regenerate → repeat until the spot depletes → move to another spot.

Bot needs:
- Stamina level (bar).
- A "no fish here" / depleted notification.
- Maybe the catch popup, to count results.

## 3. Rod fishing (the minigame — the real bot challenge)
1. **Distance.** [WIKI] You must stand at least a certain distance AWAY from a rod spot, unlike nets.
2. **Cast.** [WIKI] Hold the Cast button (default LMB) to charge; release to cast. A longer hold casts further. A cast that is too weak or too strong misses. A miss costs no stamina and no bait.
3. **Bite.** [WIKI] After a good cast, wait for a bite.
   - [ASSUMPTION] Some visual or audio cue marks the bite, and the fish bar appears. Exact cue: TO VERIFY.
4. **Fight.** [WIKI] The fish swims away; its remaining energy is the "fish bar" shown ABOVE the stamina bar.
   - Immediately hold Strafe Left/Right (default A/D) to pull in the OPPOSITE direction to the fish's swim.
   - When the fish changes direction, the fish bar turns RED. Switch to the other strafe key.
5. **Reel.** [WIKI] When the fish is "somewhat tired", a Reel option/prompt appears.
   - Release the strafe key and HOLD the Cast button (LMB) to reel. This drains the fish bar much faster.
   - If the fish starts swimming again during reeling, release LMB and go back to strafing (opposite direction).
6. Repeat 4–5 until the fish is caught.
7. **Failure.** [WIKI] Wrong inputs cost stamina. When the player runs out of stamina, the fish escapes. [WIKI/GUIDE] Reeling/fighting drains stamina throughout.
8. **Bait.** [WIKI] Without bait, junk is more likely. Bait matched to the target fish is recommended.

## 4. What this means for a bot (state machine draft)
- IDLE → CAST
  - Hold LMB for T_cast ms, then release. T_cast has to be learned per spot/distance by trial: "miss" feedback → adjust.
- WAIT_BITE → FIGHT
  - Trigger: fish bar appears.
- FIGHT: hold A or D, opposite to the fish direction.
  - The direction comes from the fish movement on screen or some UI arrow. [ASSUMPTION — TO VERIFY what the UI shows.]
  - Bar turns red → swap A/D.
- FIGHT → REEL
  - Trigger: the Reel prompt appears. Release A/D, hold LMB.
- REEL → FIGHT
  - Trigger: the fish resumes swimming. Release LMB, strafe again.
- REEL → CAUGHT: catch popup; the fish bar disappears. → back to IDLE (or move on if the spot is depleted).
- Any state → ABORT: stamina too low (wait to regenerate), target window lost, F8.

## 5. Signals to capture before coding (screen recordings / screenshots)
- The fish bar: position, colours (normal vs red), and how "empty" looks.
- The stamina bar: position, colours, empty.
- Fish direction cue: arrow? fish icon moving? line angle? THIS IS THE KEY UNKNOWN.
- The Reel prompt: text and keycap. OrcPresser's prompt reader may already detect it.
- Cast feedback: what a miss looks like, and whether there is a power meter while charging.
- The bite cue, the catch popup, and the "no fish here" text.

## 6. Risks / rules
- A rod fight needs continuous held keys with fast switching. Mistakes cost stamina and the fish, so a bot must react within ~100–200 ms. [ASSUMPTION]
- Check Jagex's rules on automation before using this in multiplayer.

(Edit freely — this text is saved to fishing_notes.md as you type.)
