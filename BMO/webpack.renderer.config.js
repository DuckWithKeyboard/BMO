const rules = require('./webpack.rules');

rules.push({
  test: /\.css$/,
  use: [{ loader: 'style-loader' }, { loader: 'css-loader' }],
});

// ✅ Added webp and gif to the image rule
rules.push({
  test: /\.(png|jpg|jpeg|gif|webp)$/i,
  type: 'asset/resource',
});

// ✅ Handle video files
rules.push({
  test: /\.(mp4|webm|ogg)$/i,
  type: 'asset/resource',
});

module.exports = {
  module: {
    rules,
  },
};