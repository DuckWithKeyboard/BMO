const rules = require('./webpack.rules');

rules.push({
  test: /\.css$/,
  use: [{ loader: 'style-loader' }, { loader: 'css-loader' }],
});

// ─── Asset rules (images, GIFs, video, audio, fonts) ──────
rules.push({
  test: /\.(png|jpe?g|gif|svg|webp|ico)$/i,
  type: 'asset/resource',
  generator: {
    filename: 'images/[name][ext]',
  },
});

rules.push({
  test: /\.(mp4|webm|ogg|ogv)$/i,
  type: 'asset/resource',
  generator: {
    filename: 'videos/[name][ext]',
  },
});

rules.push({
  test: /\.(woff2?|eot|ttf|otf)$/i,
  type: 'asset/resource',
  generator: {
    filename: 'fonts/[name][ext]',
  },
});

module.exports = {
  module: {
    rules,
  },
};