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

module.exports = {
  module: {
    rules,
  },
};