# Generated from canonical release checksums.
lookup() {
case "$1" in
market) MID='xuanyuan-os4-market'; PKG=''; CODE='2026101101'; FILE='market.zip'; SHA='1d53c4dd674930c1ed907e6b36aa71996b83860e48030fd9ba8be5ae9cb6ec1a'; TITLE='小米应用商店'; KIND='module';;
assistant) MID='xuanyuan-os4-assistant'; PKG=''; CODE='2026101105'; FILE='assistant.zip'; SHA='d2535c0d026827b5aa0c0a801ce0badc30cae515d09eb52026a4a8a1b9893537'; TITLE='智能助理负一屏'; KIND='module';;
xiaoai) MID='xuanyuan-os4-xiaoai'; PKG=''; CODE='2026101603'; FILE='xiaoai.zip'; SHA='e48db9ada307e072600a7bc9cfa90cc06d11856ef5fdd989bcb29b7255aa1f84'; TITLE='超级小爱'; KIND='module';;
phone) MID='xuanyuan-os4-phone'; PKG=''; CODE='2026101502'; FILE='phone.zip'; SHA='0b48671b8416314e504947fb942a3ba7283e9f06f4e47c7b62d04de71b8b34a0'; TITLE='电话、短信与录音'; KIND='module';;
gallery) MID='xuanyuan-os4-gallery'; PKG=''; CODE='2026101401'; FILE='gallery.zip'; SHA='77da835bcb8123f288c50ec77b5f657772c34d64dc5e65842c30863313316335'; TITLE='相册与 AI 编辑'; KIND='module';;
weather) MID='xuanyuan-os4-weather'; PKG=''; CODE='2026101302'; FILE='weather.zip'; SHA='cdfb2867fe1f6837022be655134fa6653519b60e75dda3386fca7b2dc8ae4738'; TITLE='天气与街道定位'; KIND='module';;
disaster) MID='xuanyuan-os4-disaster'; PKG=''; CODE='2026101501'; FILE='disaster.zip'; SHA='e740da5620c433bc94e1394504b9d6ec1b5c3fe8adc004b9572b39400d5d7bc3'; TITLE='自然灾害预警与报警定位'; KIND='module';;
wallet) MID='xuanyuan-os4-wallet'; PKG=''; CODE='2026101602'; FILE='wallet.zip'; SHA='2bc48b2138d0d7feb510af62317f29d739b9cf9d06eb4547552bd18cff318216'; TITLE='小米钱包与 NFC'; KIND='module';;
clock) MID=''; PKG='local.xuanyuan.mipushcompat'; CODE=''; FILE='unified.apk'; SHA='02b4d7bc35ccfa6ec9d3e7ce82171b1a96bf81ba1abb3f1dcff70170c960679f'; TITLE='时钟法定节假日'; KIND='apk';;
calendar) MID=''; PKG='com.android.calendar'; CODE=''; FILE='calendar.apk'; SHA='ed8f4356bb7c44038abbe5f215f215277c114e75de4bd21ac0a65f77d75f75f0'; TITLE='国行日历'; KIND='apk';;
mipush) MID=''; PKG='local.xuanyuan.mipushcompat'; CODE=''; FILE='unified.apk'; SHA='02b4d7bc35ccfa6ec9d3e7ce82171b1a96bf81ba1abb3f1dcff70170c960679f'; TITLE='MiPush 推送配置'; KIND='apk';;
*) return 1;;
esac
}
