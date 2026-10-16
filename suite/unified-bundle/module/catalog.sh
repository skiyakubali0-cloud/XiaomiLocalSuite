# Generated from canonical release checksums.
lookup() {
case "$1" in
market) MID='xuanyuan-os4-market'; PKG=''; CODE='2026101101'; FILE='market.zip'; SHA='1d53c4dd674930c1ed907e6b36aa71996b83860e48030fd9ba8be5ae9cb6ec1a'; TITLE='小米应用商店'; KIND='module';;
assistant) MID='xuanyuan-os4-assistant'; PKG=''; CODE='2026101105'; FILE='assistant.zip'; SHA='d2535c0d026827b5aa0c0a801ce0badc30cae515d09eb52026a4a8a1b9893537'; TITLE='智能助理负一屏'; KIND='module';;
xiaoai) MID='xuanyuan-os4-xiaoai'; PKG=''; CODE='2026101504'; FILE='xiaoai.zip'; SHA='e6bb2b36ba5e6ea4483b593c19c462d4e7ff9aba85802cbb1015bab9527f77f2'; TITLE='超级小爱'; KIND='module';;
phone) MID='xuanyuan-os4-phone'; PKG=''; CODE='2026101502'; FILE='phone.zip'; SHA='0b48671b8416314e504947fb942a3ba7283e9f06f4e47c7b62d04de71b8b34a0'; TITLE='电话、短信与录音'; KIND='module';;
gallery) MID='xuanyuan-os4-gallery'; PKG=''; CODE='2026101401'; FILE='gallery.zip'; SHA='77da835bcb8123f288c50ec77b5f657772c34d64dc5e65842c30863313316335'; TITLE='相册与 AI 编辑'; KIND='module';;
weather) MID='xuanyuan-os4-weather'; PKG=''; CODE='2026101302'; FILE='weather.zip'; SHA='cdfb2867fe1f6837022be655134fa6653519b60e75dda3386fca7b2dc8ae4738'; TITLE='天气与街道定位'; KIND='module';;
disaster) MID='xuanyuan-os4-disaster'; PKG=''; CODE='2026101501'; FILE='disaster.zip'; SHA='e740da5620c433bc94e1394504b9d6ec1b5c3fe8adc004b9572b39400d5d7bc3'; TITLE='自然灾害预警与报警定位'; KIND='module';;
wallet) MID='xuanyuan-os4-wallet'; PKG=''; CODE='2026101101'; FILE='wallet.zip'; SHA='d4d717ed5f49b5fd16d9919ccc04c6138267166090c9a8dac9938f1896ad2b8f'; TITLE='小米钱包与 NFC'; KIND='module';;
clock) MID=''; PKG='local.xuanyuan.mipushcompat'; CODE=''; FILE='unified.apk'; SHA='660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25'; TITLE='时钟法定节假日'; KIND='apk';;
calendar) MID=''; PKG='com.android.calendar'; CODE=''; FILE='calendar.apk'; SHA='ed8f4356bb7c44038abbe5f215f215277c114e75de4bd21ac0a65f77d75f75f0'; TITLE='国行日历'; KIND='apk';;
mipush) MID=''; PKG='local.xuanyuan.mipushcompat'; CODE=''; FILE='unified.apk'; SHA='660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25'; TITLE='MiPush 推送配置'; KIND='apk';;
*) return 1;;
esac
}
