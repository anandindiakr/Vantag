/**
 * babel.config.js
 * ================
 * Babel configuration for Expo with NativeWind (Tailwind CSS) support.
 *
 * NativeWind v4 requires:
 *  - babel-preset-expo as the base preset
 *  - nativewind/babel as a plugin (transforms className to style props)
 *
 * Usage:
 *   The tailwind.config.js content option must include all component files.
 */

module.exports = function (api) {
  api.cache(true);

  return {
    presets: [
      [
        "babel-preset-expo",
        {
          jsxImportSource: "nativewind",
        },
      ],
    ],
    plugins: [
      // NativeWind v4 class-name → style transformation
      "nativewind/babel",

      // React Native Reanimated plugin (required by react-navigation gestures)
      // Must be listed LAST among plugins.
      "react-native-reanimated/plugin",
    ],
  };
};
