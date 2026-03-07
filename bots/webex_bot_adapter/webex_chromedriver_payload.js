(function () {
  // Minimal payload for Webex until provider-specific media hooks are added.
  // The adapter uses these APIs opportunistically, so no-op implementations
  // keep the flow stable in environments where meeting internals are unavailable.
  window.ws = window.ws || {
    enableMediaSending: function () {},
    disableMediaSending: function () {},
  };

  window.botOutputManager = window.botOutputManager || {
    isVideoPlaying: function () {
      return false;
    },
    playVideo: function () {},
    displayImage: function () {},
    playPCMAudio: function () {},
    getBotOutputPeerConnectionOffer: function () {
      return { error: "not_supported_for_webex" };
    },
    startBotOutputPeerConnection: function () {},
  };
})();
