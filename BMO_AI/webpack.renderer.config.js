const rules = require('./webpack.rules');

// CSS
rules.push({
  test: /\.css$/,
  use: [{ loader: 'style-loader' }, { loader: 'css-loader' }],
});

// Images — webpack 5 asset/resource emits each file to the output
// directory and gives you the resolved URL as the import value.
rules.push({
  test: /\.(png|jpe?g|gif|svg|webp)$/i,
  type: 'asset/resource',
});

// Audio — same treatment as images; import gives you the resolved URL.
rules.push({
  test: /\.(wav|mp3|ogg|flac)$/i,
  type: 'asset/resource',
});

module.exports = {
  module: {
    rules,
  },
};