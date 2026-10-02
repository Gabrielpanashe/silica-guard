// Metro config (2 October 2026, design revamp) — added so the icon SVGs
// exported from the Figma redesign (assets/icons/*.svg) can be imported as
// React components via react-native-svg-transformer. Everything else is
// Expo's default config, untouched.
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.transformer = {
  ...config.transformer,
  babelTransformerPath: require.resolve('react-native-svg-transformer/expo'),
};
config.resolver = {
  ...config.resolver,
  assetExts: config.resolver.assetExts.filter((ext) => ext !== 'svg'),
  sourceExts: [...config.resolver.sourceExts, 'svg'],
};

module.exports = config;
