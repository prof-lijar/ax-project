# VoyagerI name, logo and Windows taskbar icon

Date: 2026-11-20 (Asia/Seoul)

The app's display name is **VoyagerI**. The refreshed icon uses an ivory
V-shaped spacecraft and a mint navigation star on midnight navy. It replaces
the original yellow chat/relay/checkmark logo in the app and Windows resources.

## Integration

- `app/assets/voyageri.png`: final logo source, generated using the built-in image tool.
- `app/assets/voyageri.ico`: Windows icon with 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256 px frames.
- `app/branding.py`: shared name, resource resolution and Qt application icon.
- Startup calls `SetCurrentProcessExplicitAppUserModelID("Nextor.VoyagerI.Desktop")`
  before creating Qt UI so source launches have their own Windows taskbar identity.
- Main window and Settings use the same icon. The header replaces its old K badge
  with the actual logo.
- `KakaoCaptureAgent.spec` retains its build-entry filename but creates `VoyagerI.exe`,
  bundles both assets and embeds the ICO and Windows product/version resource.
- The existing Windows release workflow packages `VoyagerI-v<VERSION>-windows-x64.exe`.
  Existing release tag prefixes remain accepted. The Windows release workflow builds
  and publishes the versioned executable and SHA-256 checksum.

Resource lookup is relative to `app/branding.py`, supporting source launches and
PyInstaller's extracted bundle without relying on the working directory.
Package data includes the PNG/ICO for installed Python packages as well.
Existing storage directories, credential keys, startup registration and mutex IDs
are retained to preserve configuration and prevent a second instance during upgrades.

The taskbar initialization follows [Microsoft's startup requirement](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid).
Bundled resource lookup follows [PyInstaller's runtime guidance](https://www.pyinstaller.org/en/stable/runtime-information.html).

## Build and check

On Windows, from `software/kakao-capture-agent`:

```powershell
.\build.ps1
.\dist\VoyagerI.exe
```

The build runs source and packaged startup checks, including loading the icon and
checking the new window title. The ICO is committed, so builds require no image
service. To regenerate its resolution frames from the PNG:

```powershell
uv run python tools/build_icon.py
```

Close the old executable and launch the rebuilt one. If a previously pinned
shortcut still shows the old name/icon, unpin it and pin the new `VoyagerI.exe`.
The currently installed executable cannot acquire a new embedded icon without a rebuild.

Portable Qt checks verify all ICO frames decode, the application and window load
the new icon, and the mocked Windows API receives the stable Unicode AppUserModelID.
A real Windows taskbar and packaged EXE still require Windows validation; this
Linux workspace does not build or visually inspect a Windows taskbar.

## Image generation record

The artwork was generated under the working name TalkRelay. The user subsequently
selected VoyagerI; the wordless logo is retained and the original prompts below
remain unchanged as a historical record.

Mode: built-in `image_gen`, followed only by format/resolution packaging for ICO.
No CLI/API fallback was used. The final PNG is copied into the project, with its
original generated file preserved. The prompts are recorded below for reproducibility.

Initial prompt:

> Use case: logo-brand. Create the final square desktop application icon for TalkRelay, a Korean chat capture and workflow assistant. One bold, beautifully balanced flat symbol: a warm golden-yellow rounded-square tile, with a deep charcoal speech-bubble silhouette containing a single simple yellow bent relay arrow/check shape. The symbol expresses receiving a chat request and completing a workflow. No lettering. Strong silhouette, thick clean shapes, generous inner padding, legible at 16x16 and 32x32 pixels. Refined minimal vector-like finish, crisp edges, no gradients, no shadows, no texture, no mockup, no decorative sparkles. The rounded square fills about 90 percent of the square canvas; only the outside corners/margin are genuinely transparent. Use the existing app's warm yellow and dark charcoal visual character. Deliver exactly one centered icon, no variants or presentation sheet.

First refinement:

> Edit this TalkRelay app icon. Preserve the exact composition: yellow rounded square, dark speech bubble, yellow relay arrow and checkmark. Clean production icon edges: remove ALL stray yellow speckles, fragments, roughness, noise and glow OUTSIDE the rounded-square tile. Outside the single clean tile silhouette must be completely transparent. Make the tile and symbol fills smooth flat solid colors, removing mottled texture and gradients. Leave a uniform clean transparent margin of 5 percent on every side. Crisp geometric antialiased boundaries, no shadow. Do not add text, objects, shapes or detail. Deliver one square PNG desktop icon.

Final prompt (opaque square to avoid generated transparent-edge artifacts):

> Turn this into a perfectly clean FULL-BLEED SQUARE desktop app icon. Preserve the central charcoal speech bubble, yellow relay arrow and checkmark exactly. Replace the whole backdrop with one continuous solid warm yellow color extending to every outer edge and all four canvas corners. NO rounded outer tile, NO transparent pixels, NO black exterior, NO speckles or edge effects, NO border or margin. Only the charcoal speech bubble on a solid yellow square with the yellow arrow and tick. Flat clean solid fills. One 1024x1024 square icon, no text, no presentation.

## Validation results

- 17 focused tests passed; 1 platform-specific test skipped (`test_branding`,
  `test_gui`, `test_settings_save`).
- Python lint and whitespace checks passed.
- All ten PNG-compressed 32-bit ICO frames decoded in Qt.
- The source Qt window was rendered offscreen with synthetic data and visually
  inspected; the logo and bilingual title are visible in the header.
- Spec resource paths, renamed executable identity and version-resource syntax
  were checked without invoking a Windows compiler.
- Local Linux checks do not build a Windows executable; the Windows release
  workflow runs native tests, builds the EXE and verifies its packaged startup.


## Refreshed VoyagerI artwork — 2026-11-20

Generated with the built-in `image_gen` tool. The final PNG replaces the earlier
logo at `app/assets/voyageri.png`; `tools/build_icon.py` regenerates the ten ICO
resolutions at `app/assets/voyageri.ico`. The app, taskbar and executable all
reuse these resource paths. Earlier prompts above are historical provenance.

Prompt:

> Use case: logo-brand. Design a completely new polished desktop application icon for VoyagerI, an assistant that watches chat messages and carries requests through workflows. A minimal bold ivory V-shaped spacecraft / forward chevron, with one small vivid mint four-point navigation star beside its upper-right tip. The lower V subtly forms the tail of a chat bubble; balance the mark as one distinctive compact symbol, not a collection of icons. Full-bleed perfectly square deep midnight-navy background, solid color all the way to every edge and corner, no transparency and no outer rounded tile. Ivory and mint accents only. Strong clean silhouette, generous padding, thick shapes legible at 16 and 32 pixels. Flat vector-like graphic, smooth sharp geometry. No text, letters spelling the name, gradients, texture, shadows, 3D effects, mockup or extra decorations. One final centered square app icon, not multiple variants.


## Silent auto-run startup — 2026-11-20

Run Agent (auto) suppresses the optional queued worker greeting. Arming records
its baseline and resumes queued work without submitting or changing chat text.
The dedicated legacy device/Bizgo button retains its separate greeting policy.
The overview shows Watching for new messages, with a Watching button and status
badge while auto-run is active; paused/stopped states restore the action label.
Existing pending requests still resume and normal API replies remain unchanged.

Validation: 96 workflow/queue/GUI tests and 3 icon/identity tests passed. The
integration test asserts zero sender/API calls during first start and restart,
then exactly one unchanged API reply after a new message. The updated Watching
screen and logo were also rendered with synthetic data and visually inspected.
Windows packaging is checked by the release workflow before publication.
