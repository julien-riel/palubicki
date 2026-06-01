// palubicki — reference vertex-attribute wind shader (export pipeline P1).
//
// Consumes the portable wind contract palubicki bakes into every tree primitive
// (see geom/wind.py + docs/export-pipeline-design.md §6.1) and drives a
// hierarchical Crysis/GPU-Gems-style sway entirely in the vertex shader, with no
// skeleton. This is the *reference* consumer — each target engine writes its own
// shader against the same attributes; only the GLSL differs.
//
// Attribute mapping (three.js r144 GLTFLoader names in parentheses):
//   COLOR_0    (color)      = (phase, stiffness, leafMask)
//   COLOR_1    (color_1)    = tint (autumn / bark age) — multiplied into diffuse
//   TEXCOORD_1 (uv2)        = (pivot.x, pivot.y)
//   TEXCOORD_2 (texcoord_2) = (pivot.z, wind_tier)
//
// COLOR_0 holds wind data, NOT colour, so we force `vertexColors = false` and read
// `color` ourselves — otherwise a vanilla viewer would tint the tree by its phase
// /stiffness values. The tint that *should* show rides COLOR_1, re-applied here.
(function (global) {
  "use strict";

  function createUniforms() {
    return {
      uTime: { value: 0.0 },
      uWindDir: { value: new THREE.Vector3(1.0, 0.0, 0.35).normalize() },
      uGustStrength: { value: 1.0 },   // 0 = dead calm; the UI toggle drives this
      uTreeHeight: { value: 5.0 },     // set per-tree from the loaded bbox
    };
  }

  function tick(uniforms, dt) {
    uniforms.uTime.value += dt;
  }

  // Walk a loaded glTF scene and patch every tree material to read the wind
  // contract. Meshes without the wind attribute (e.g. obstacles) are left alone.
  function apply(root, uniforms) {
    root.traverse(function (obj) {
      if (!obj.isMesh || !obj.geometry) return;
      const g = obj.geometry;
      if (!g.attributes.color) return; // no COLOR_0 wind stream → not a tree primitive
      const flags = {
        hasPivot: !!g.attributes.uv2 && !!g.attributes.texcoord_2,
        hasTint: !!g.attributes.color_1,
      };
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
      for (const m of mats) patchMaterial(m, uniforms, flags);
    });
  }

  function patchMaterial(material, uniforms, flags) {
    // COLOR_0 is wind, not colour — stop three from auto-multiplying it into diffuse.
    material.vertexColors = false;
    material.onBeforeCompile = function (shader) {
      shader.uniforms.uTime = uniforms.uTime;
      shader.uniforms.uWindDir = uniforms.uWindDir;
      shader.uniforms.uGustStrength = uniforms.uGustStrength;
      shader.uniforms.uTreeHeight = uniforms.uTreeHeight;

      const pivotDecl = flags.hasPivot
        ? "attribute vec2 uv2;\nattribute vec2 texcoord_2;\n"
        : "";
      const tintVarying = flags.hasTint ? "varying vec3 vTint;\n" : "";

      shader.vertexShader = shader.vertexShader
        .replace(
          "#include <common>",
          [
            "#include <common>",
            "uniform float uTime;",
            "uniform vec3  uWindDir;",
            "uniform float uGustStrength;",
            "uniform float uTreeHeight;",
            "attribute vec3 color;   // (phase, stiffness, leafMask)",
            pivotDecl,
            tintVarying,
            "const float WIND_TAU = 6.28318530718;",
            "vec3 palWind(vec3 pos, vec3 nrm, vec3 w, vec3 pivot, float tierVal) {",
            "  float phase = w.x; float stiffness = w.y; float leafMask = w.z;",
            "  float flex = 1.0 - clamp(stiffness, 0.0, 1.0);", // thin whips, thick barely moves
            "  float g = uGustStrength;",
            "  vec3 disp = vec3(0.0);",
            "  // Tier 0 — whole-tree sway, growing with height above the collar.",
            "  float h = clamp(pos.y / max(uTreeHeight, 1e-3), 0.0, 1.0);",
            "  disp += uWindDir * (g * 0.05 * h * h) * sin(uTime * 0.9);",
            "  // Tier 1+ — each branch swings about its pivot; tip (far from pivot) moves",
            "  // most. arm is clamped so the longest branches sway tastefully, not fling.",
            "  if (tierVal >= 0.5) {",
            "    vec3 r = pos - pivot; float arm = min(length(r), 2.0);",
            "    float bp = uTime * 1.7 + phase * WIND_TAU;",
            "    disp += uWindDir * (g * 0.18 * flex * arm) * sin(bp);",
            "    disp.y += (g * 0.05 * flex * arm) * sin(0.5 * bp);",
            "  }",
            "  // Tier 2 — per-leaf flutter along the blade normal.",
            "  if (leafMask > 0.5) {",
            "    disp += nrm * (g * 0.035) * sin(uTime * 3.4 + phase * WIND_TAU);",
            "  }",
            "  return disp;",
            "}",
          ].join("\n")
        )
        .replace(
          "#include <begin_vertex>",
          [
            "#include <begin_vertex>",
            flags.hasPivot
              ? "vec3 palPivot = vec3(uv2.x, uv2.y, texcoord_2.x); float palTier = texcoord_2.y;"
              : "vec3 palPivot = vec3(0.0); float palTier = 0.0;",
            "transformed += palWind(transformed, objectNormal, color, palPivot, palTier);",
            flags.hasTint ? "vTint = color_1;" : "",
          ].join("\n")
        );

      if (flags.hasTint) {
        shader.vertexShader = "attribute vec3 color_1;\n" + shader.vertexShader;
        shader.fragmentShader = shader.fragmentShader
          .replace("#include <common>", "#include <common>\nvarying vec3 vTint;")
          .replace(
            "#include <color_fragment>",
            "#include <color_fragment>\ndiffuseColor.rgb *= vTint;"
          );
      }
    };
    // Distinct cache keys so three doesn't share a program across the tint/no-tint
    // and pivot/no-pivot variants.
    material.customProgramCacheKey = function () {
      return "palWind:" + (flags.hasPivot ? "p" : "") + (flags.hasTint ? "t" : "");
    };
    material.needsUpdate = true;
  }

  global.WindFX = { createUniforms, tick, apply };
})(window);
