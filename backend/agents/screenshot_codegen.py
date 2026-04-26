"""
Phase 3a — screenshot harness codegen.

Reads the Phase 2 app map + each screen's Dart source, infers the screen class
name and constructor parameters, and generates a Dart test file that pumps
each screen at multiple resolutions and writes PNGs.

Pure mechanical codegen. No AI. No external Dart packages — uses only what
ships with the Flutter SDK (flutter, flutter_test, dart:io, dart:ui).
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Mobile-only resolutions. No tablet by default — easy to extend.
DEFAULT_RESOLUTIONS = [
    (320, 568),   # iPhone SE 1st gen — smallest common modern screen
    (393, 852),   # iPhone 15 / 15 Pro
    (412, 915),   # Pixel 7 / typical Android
    (768, 1024),  # iPad Mini portrait — catches "tablet too narrow" bugs
]

# Map Dart primitive types to safe stub literals for placeholder constructor args.
PRIMITIVE_STUBS = {
    "String": "''",
    "int": "0",
    "double": "0.0",
    "num": "0",
    "bool": "false",
}


@dataclass
class ScreenInfo:
    rel_path: str             # e.g. lib/screens/home_screen.dart
    class_name: str           # e.g. HomeScreen
    required_params: List[tuple[str, str]] = field(default_factory=list)  # (type, name)
    skip_reason: Optional[str] = None  # set when we can't auto-stub


# Match top-level widget class declarations.
RE_WIDGET_CLASS = re.compile(
    r"^class\s+(\w+)\s+extends\s+(?:StatelessWidget|StatefulWidget|ConsumerWidget|HookWidget)\b",
    re.MULTILINE,
)

# Match the const constructor of a widget. We only inspect the FIRST one — most
# screens have a single canonical constructor.
RE_CONSTRUCTOR = re.compile(
    r"const\s+(\w+)\s*\(\s*\{([^}]*)\}\s*\)\s*[:;]"
)

# Pull `required this.foo` and `required Type foo` from constructor body.
RE_REQUIRED_PARAM = re.compile(
    r"required\s+(?:(\w[\w<>?, ]*)\s+)?this\.(\w+)|required\s+(\w[\w<>?, ]*)\s+(\w+)"
)

# When we see `final Type name;` at class body, remember the type for `this.name`.
RE_FIELD_DECL = re.compile(
    r"final\s+(\w[\w<>?, ]*)\s+(\w+)\s*;"
)


def _parse_screen(rel_path: str, source: str) -> Optional[ScreenInfo]:
    """Pull screen class name and required constructor params from Dart source."""
    m = RE_WIDGET_CLASS.search(source)
    if not m:
        return None
    class_name = m.group(1)

    # Build a Type lookup for `final Type name;` field declarations so we can
    # resolve `required this.name` to the field's type. Regex captures (type, name);
    # we want name → type lookup.
    field_types = {name: typ for typ, name in RE_FIELD_DECL.findall(source)}

    required: list[tuple[str, str]] = []
    ctor = RE_CONSTRUCTOR.search(source)
    if ctor:
        body = ctor.group(2)
        for m in RE_REQUIRED_PARAM.finditer(body):
            # Either group 1+2 (this.name) or group 3+4 (typed)
            if m.group(2):
                pname = m.group(2)
                ptype = m.group(1) or field_types.get(pname, "Object")
            else:
                ptype = m.group(3)
                pname = m.group(4)
            required.append((ptype.strip(), pname.strip()))

    info = ScreenInfo(rel_path=rel_path, class_name=class_name, required_params=required)

    # Decide if we can synthesize stubs for every required param.
    for ptype, _ in required:
        base = ptype.split("<")[0].rstrip("?")
        if base not in PRIMITIVE_STUBS:
            info.skip_reason = (
                f"requires non-primitive constructor arg of type `{ptype}`"
            )
            break
    return info


def _stub_arg(param: tuple[str, str]) -> str:
    ptype, pname = param
    base = ptype.split("<")[0].rstrip("?")
    return f"{pname}: {PRIMITIVE_STUBS[base]}"


def _read_pubspec_name(project_root: Path) -> str:
    pubspec = project_root / "pubspec.yaml"
    for line in pubspec.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    raise RuntimeError(f"Could not find package name in {pubspec}")


def _rel_to_package_import(rel_path: str, package_name: str) -> str:
    """Convert lib/screens/home_screen.dart -> package:my_app/screens/home_screen.dart"""
    posix = rel_path.replace("\\", "/")
    if posix.startswith("lib/"):
        posix = posix[len("lib/"):]
    return f"package:{package_name}/{posix}"


def _render_dart(package_name: str, screens: List[ScreenInfo],
                 resolutions: List[tuple[int, int]]) -> str:
    """Build the Dart harness file as a single string."""
    runnable = [s for s in screens if s.skip_reason is None]
    skipped = [s for s in screens if s.skip_reason is not None]

    imports = "\n".join(
        f"import '{_rel_to_package_import(s.rel_path, package_name)}';"
        for s in runnable
    )

    res_list = ",\n  ".join(f"Size({w}.0, {h}.0)" for w, h in resolutions)

    def render_screen_block(s: ScreenInfo) -> str:
        ctor_args = ", ".join(_stub_arg(p) for p in s.required_params)
        widget_expr = f"{s.class_name}({ctor_args})"
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", Path(s.rel_path).stem).lower()
        # NOTE: Python f-string escapes — `{{` → `{`, `}}` → `}`, `$` is literal,
        # so Dart string interpolation `${size...}` becomes `${{size...}}` in the
        # template, and a bare `$tag` stays as-is.
        return f"""
  for (final size in resolutions) {{
    final tag = '${{size.width.toInt()}}x${{size.height.toInt()}}';
    testWidgets('{s.class_name} @ $tag', (tester) async {{
      tester.view.physicalSize = size;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(() {{
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      }});

      await tester.pumpWidget(MaterialApp(home: {widget_expr}));
      // Bound the wait — without this `pumpAndSettle` can hang for 10 minutes
      // on screens with infinite Timers / unresolved Futures (FutureBuilder,
      // shared_preferences mock waits, etc.).
      try {{
        await tester.pumpAndSettle(
          const Duration(milliseconds: 100),
          EnginePhase.sendSemanticsUpdate,
          const Duration(seconds: 4),
        );
      }} catch (_) {{
        await tester.pump(const Duration(milliseconds: 500));
      }}

      // Walk the render tree to find the first RepaintBoundary
      // (MaterialApp wraps its content in one).
      RenderRepaintBoundary? rb;
      void visit(RenderObject node) {{
        if (rb != null) return;
        if (node is RenderRepaintBoundary) {{ rb = node; return; }}
        node.visitChildren(visit);
      }}
      final root = tester.binding.rootElement?.findRenderObject();
      if (root != null) visit(root);

      if (rb == null) {{
        debugPrint('No RepaintBoundary found for {s.class_name} @ $tag — skipping.');
        return;
      }}

      final image = await rb!.toImage(pixelRatio: 1.0);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      final dir = Directory('test/_flowtest_screenshots/{slug}');
      dir.createSync(recursive: true);
      File('${{dir.path}}/$tag.png')
        .writeAsBytesSync(bytes!.buffer.asUint8List());
    }}, timeout: const Timeout(Duration(seconds: 10)));
  }}
"""

    blocks = "\n".join(render_screen_block(s) for s in runnable)
    skip_comment = "\n".join(
        f"//   - {s.rel_path}: {s.skip_reason}" for s in skipped
    )
    skip_header = (
        f"// Skipped screens (auto-stubbing not safe):\n{skip_comment}\n"
        if skipped else ""
    )

    return f"""// AUTO-GENERATED by FlowTest AI Phase 3a. DO NOT EDIT BY HAND.
// Re-running step3_visual.py will overwrite this file.
{skip_header}
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart' show FontLoader;
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart' show SharedPreferences;

{imports}

const resolutions = <Size>[
  {res_list},
];

class _StubHttpOverrides extends HttpOverrides {{
  @override
  HttpClient createHttpClient(SecurityContext? context) {{
    final client = super.createHttpClient(context);
    client.badCertificateCallback = (_, __, ___) => true;
    return client;
  }}
}}

/// Load Roboto + Material Icons from the Flutter SDK install so widget tests
/// render real glyphs instead of Ahem boxes. Without this, screenshots are
/// useless for any text-related visual analysis.
Future<void> _loadFonts() async {{
  final flutterRoot = Platform.environment['FLUTTER_ROOT'];
  if (flutterRoot == null) return;
  final fontsDir = '$flutterRoot/bin/cache/artifacts/material_fonts';

  Future<void> tryLoad(String family, List<String> filenames) async {{
    final loader = FontLoader(family);
    var any = false;
    for (final fn in filenames) {{
      final file = File('$fontsDir/$fn');
      if (!file.existsSync()) continue;
      final bytes = await file.readAsBytes();
      loader.addFont(Future.value(ByteData.view(bytes.buffer)));
      any = true;
    }}
    if (any) await loader.load();
  }}

  await tryLoad('Roboto', [
    'Roboto-Regular.ttf',
    'Roboto-Bold.ttf',
    'Roboto-Italic.ttf',
    'Roboto-Medium.ttf',
    'Roboto-Light.ttf',
  ]);
  await tryLoad('MaterialIcons', ['MaterialIcons-Regular.otf']);
}}

void main() {{
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = _StubHttpOverrides();

  setUpAll(() async {{
    await _loadFonts();
    SharedPreferences.setMockInitialValues(<String, Object>{{}});
  }});
{blocks}
}}
"""


def generate_harness(project_root: str | Path, app_map_path: str | Path,
                     output_dir_name: str = "test",
                     resolutions: Optional[List[tuple[int, int]]] = None) -> dict:
    """Build the harness Dart file in <project>/<output_dir_name>/.

    Returns a dict summary: {harness_path, runnable, skipped, resolutions}.
    """
    project_root = Path(project_root).resolve()
    app_map = json.loads(Path(app_map_path).read_text(encoding="utf-8"))
    package_name = _read_pubspec_name(project_root)
    resolutions = resolutions or DEFAULT_RESOLUTIONS

    screens: List[ScreenInfo] = []
    for s in app_map.get("screens", []):
        rel = s.get("file")
        if not rel:
            continue
        path = project_root / rel
        if not path.is_file():
            continue
        info = _parse_screen(rel, path.read_text(encoding="utf-8"))
        if info:
            screens.append(info)

    if not screens:
        raise RuntimeError("No parseable screens found in app map.")

    dart = _render_dart(package_name, screens, resolutions)
    harness_path = project_root / output_dir_name / "_flowtest_screenshots_test.dart"
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_path.write_text(dart, encoding="utf-8")

    runnable = [s for s in screens if s.skip_reason is None]
    skipped = [s for s in screens if s.skip_reason is not None]
    return {
        "harness_path": str(harness_path),
        "package": package_name,
        "runnable": [s.class_name for s in runnable],
        "skipped": [{"class": s.class_name, "reason": s.skip_reason} for s in skipped],
        "resolutions": resolutions,
    }


if __name__ == "__main__":
    import sys
    project = sys.argv[1]
    app_map = sys.argv[2] if len(sys.argv) > 2 else "backend/logs/app_map.json"
    out = generate_harness(project, app_map)
    print(json.dumps(out, indent=2))
