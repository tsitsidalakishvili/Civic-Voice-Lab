from pathlib import Path
import shutil
import tempfile

import streamlit.components.v1 as components


_PATCH_MARKER = "/* FS_SWIPE_DOWN_PASS_PATCH_V29 */"


def _replace_all(content, replacements):
    updated = content
    for old, new in replacements:
        updated = updated.replace(old, new)
    return updated


def _js_replacements():
    return [
        (
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeLeft()" disabled>❌</button>',
            '<button class="action-btn btn-disagree" onclick="swipeCards.swipeLeft()" disabled><span class="fs-swipe-icon fs-left" aria-hidden="true"></span><span class="fs-swipe-copy"><b>DISAGREE</b><small>SWIPE LEFT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-disagree" onclick="swipeCards.swipeLeft()" disabled>DISAGREE</button>',
            '<button class="action-btn btn-disagree" onclick="swipeCards.swipeLeft()" disabled><span class="fs-swipe-icon fs-left" aria-hidden="true"></span><span class="fs-swipe-copy"><b>DISAGREE</b><small>SWIPE LEFT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeLeft()">❌</button>',
            '<button class="action-btn btn-disagree" onclick="swipeCards.swipeLeft()"><span class="fs-swipe-icon fs-left" aria-hidden="true"></span><span class="fs-swipe-copy"><b>DISAGREE</b><small>SWIPE LEFT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-disagree" onclick="swipeCards.swipeLeft()">DISAGREE</button>',
            '<button class="action-btn btn-disagree" onclick="swipeCards.swipeLeft()"><span class="fs-swipe-icon fs-left" aria-hidden="true"></span><span class="fs-swipe-copy"><b>DISAGREE</b><small>SWIPE LEFT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()" disabled>✔️</button>',
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()" disabled><span class="fs-swipe-icon fs-right" aria-hidden="true"></span><span class="fs-swipe-copy"><b>AGREE</b><small>SWIPE RIGHT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()" disabled>AGREE</button>',
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()" disabled><span class="fs-swipe-icon fs-right" aria-hidden="true"></span><span class="fs-swipe-copy"><b>AGREE</b><small>SWIPE RIGHT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()">✔️</button>',
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()"><span class="fs-swipe-icon fs-right" aria-hidden="true"></span><span class="fs-swipe-copy"><b>AGREE</b><small>SWIPE RIGHT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()">AGREE</button>',
            '<button class="action-btn btn-like" onclick="swipeCards.swipeRight()"><span class="fs-swipe-icon fs-right" aria-hidden="true"></span><span class="fs-swipe-copy"><b>AGREE</b><small>SWIPE RIGHT</small></span></button>',
        ),
        (
            '<button class="action-btn btn-back" onclick="swipeCards.goBack()">',
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeDown()"><span class="fs-swipe-icon fs-down" aria-hidden="true"></span><span class="fs-swipe-copy"><b>PASS</b><small>SWIPE DOWN</small></span></button>\n'
            '          <button class="action-btn btn-back" onclick="swipeCards.goBack()">',
        ),
        (
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeDown()">PASS</button>',
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeDown()"><span class="fs-swipe-icon fs-down" aria-hidden="true"></span><span class="fs-swipe-copy"><b>PASS</b><small>SWIPE DOWN</small></span></button>',
        ),
        (
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeDown()" disabled>PASS</button>',
            '<button class="action-btn btn-pass" onclick="swipeCards.swipeDown()" disabled><span class="fs-swipe-icon fs-down" aria-hidden="true"></span><span class="fs-swipe-copy"><b>PASS</b><small>SWIPE DOWN</small></span></button>',
        ),
        (
            '<button class="action-btn btn-back" onclick="swipeCards.goBack()">\n'
            '            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
            '              <path d="M12 3C16.9706 3 21 7.02944 21 12C21 16.9706 16.9706 21 12 21C8.5 21 5.5 18.5 4 15.5" stroke="#FFA500" stroke-width="2.5" stroke-linecap="round" fill="none"/>\n'
            '              <path d="M2 14L4 12.5L6 14" stroke="#FFA500" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>\n'
            '            </svg>\n'
            '          </button>',
            '',
        ),
        (
            '<button class="action-btn btn-back" onclick="swipeCards.goBack()">\n'
            '          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">\n'
            '            <path d="M12 3C16.9706 3 21 7.02944 21 12C21 16.9706 16.9706 21 12 21C8.5 21 5.5 18.5 4 15.5" stroke="#FFA500" stroke-width="2.5" stroke-linecap="round" fill="none"/>\n'
            '            <path d="M2 16L4 13L6 16" stroke="#FFA500" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>\n'
            '          </svg>\n'
            '        </button>',
            '',
        ),
        (
            '<div class="action-indicator like">✔️</div>\n          <div class="action-indicator pass">❌</div>',
            '<div class="action-indicator like"><span class="fs-swipe-icon fs-right"></span><span class="fs-ind-copy"><b>AGREE</b><small>SWIPE RIGHT</small></span></div>\n'
            '          <div class="action-indicator pass"><span class="fs-swipe-icon fs-left"></span><span class="fs-ind-copy"><b>DISAGREE</b><small>SWIPE LEFT</small></span></div>\n'
            '          <div class="action-indicator down"><span class="fs-swipe-icon fs-down"></span><span class="fs-ind-copy"><b>PASS</b><small>SWIPE DOWN</small></span></div>',
        ),
        (
            '<div class="action-indicator like">AGREE</div>\n'
            '          <div class="action-indicator pass">DISAGREE</div>\n'
            '          <div class="action-indicator down">PASS</div>',
            '<div class="action-indicator like"><span class="fs-swipe-icon fs-right"></span><span class="fs-ind-copy"><b>AGREE</b><small>SWIPE RIGHT</small></span></div>\n'
            '          <div class="action-indicator pass"><span class="fs-swipe-icon fs-left"></span><span class="fs-ind-copy"><b>DISAGREE</b><small>SWIPE LEFT</small></span></div>\n'
            '          <div class="action-indicator down"><span class="fs-swipe-icon fs-down"></span><span class="fs-ind-copy"><b>PASS</b><small>SWIPE DOWN</small></span></div>',
        ),
        (
            "          const likeIndicator = topCard.querySelector('.action-indicator.like');\n"
            "          const passIndicator = topCard.querySelector('.action-indicator.pass');\n\n"
            "          if (deltaX > 50) {\n"
            "            likeIndicator.classList.add('show');\n"
            "            passIndicator.classList.remove('show');\n"
            "          } else if (deltaX < -50) {\n"
            "            passIndicator.classList.add('show');\n"
            "            likeIndicator.classList.remove('show');\n"
            "          } else {\n"
            "            likeIndicator.classList.remove('show');\n"
            "            passIndicator.classList.remove('show');\n"
            "          }",
            "          const likeIndicator = topCard.querySelector('.action-indicator.like');\n"
            "          const passIndicator = topCard.querySelector('.action-indicator.pass');\n"
            "          const downIndicator = topCard.querySelector('.action-indicator.down');\n\n"
            "          const isDownGesture = deltaY > 50 && Math.abs(deltaY) > Math.abs(deltaX) + 20;\n"
            "          if (isDownGesture) {\n"
            "            downIndicator.classList.add('show');\n"
            "            likeIndicator.classList.remove('show');\n"
            "            passIndicator.classList.remove('show');\n"
            "          } else if (deltaX > 50) {\n"
            "            likeIndicator.classList.add('show');\n"
            "            passIndicator.classList.remove('show');\n"
            "            downIndicator.classList.remove('show');\n"
            "          } else if (deltaX < -50) {\n"
            "            passIndicator.classList.add('show');\n"
            "            likeIndicator.classList.remove('show');\n"
            "            downIndicator.classList.remove('show');\n"
            "          } else {\n"
            "            likeIndicator.classList.remove('show');\n"
            "            passIndicator.classList.remove('show');\n"
            "            downIndicator.classList.remove('show');\n"
            "          }",
        ),
        (
            "    const deltaX = this.currentX - this.startX;\n"
            "    const topCard = this.container.querySelector('.swipe-card:first-child');\n"
            "    \n"
            "    if (topCard) {\n"
            "      topCard.classList.remove('dragging');\n"
            "      \n"
            "      // Determine swipe direction\n"
            "      if (Math.abs(deltaX) > 100) {\n"
            "        if (deltaX > 0) {\n"
            "          this.swipeRight();\n"
            "        } else {\n"
            "          this.swipeLeft();\n"
            "        }\n"
            "      } else {\n"
            "        // Snap back to center\n"
            "        topCard.style.transform = '';\n"
            "        topCard.querySelector('.action-indicator.like').classList.remove('show');\n"
            "        topCard.querySelector('.action-indicator.pass').classList.remove('show');\n"
            "      }\n"
            "    }",
            "    const deltaX = this.currentX - this.startX;\n"
            "    const deltaY = this.currentY - this.startY;\n"
            "    const topCard = this.container.querySelector('.swipe-card:first-child');\n"
            "    \n"
            "    if (topCard) {\n"
            "      topCard.classList.remove('dragging');\n"
            "      \n"
            "      // Determine swipe direction\n"
            "      if (deltaY > 100 && Math.abs(deltaY) > Math.abs(deltaX) + 20) {\n"
            "        this.swipeDown();\n"
            "      } else if (Math.abs(deltaX) > 100) {\n"
            "        if (deltaX > 0) {\n"
            "          this.swipeRight();\n"
            "        } else {\n"
            "          this.swipeLeft();\n"
            "        }\n"
            "      } else {\n"
            "        // Snap back to center\n"
            "        topCard.style.transform = '';\n"
            "        topCard.querySelector('.action-indicator.like').classList.remove('show');\n"
            "        topCard.querySelector('.action-indicator.pass').classList.remove('show');\n"
            "        topCard.querySelector('.action-indicator.down').classList.remove('show');\n"
            "      }\n"
            "    }",
        ),
        (
            "  goBack() {",
            "  swipeDown() {\n"
            "    if (this.mode !== 'swipe') {\n"
            "      this.showNotification('Press \"Swipe\" to be able to swipe');\n"
            "      return;\n"
            "    }\n"
            "    if (this.isAnimating) return;\n"
            "    this.isAnimating = true;\n"
            "    const topCard = this.container.querySelector('.swipe-card:first-child');\n"
            "    const card = this.cards[this.currentIndex];\n"
            "\n"
            "    if (topCard && card) {\n"
            "      topCard.classList.add('swiped-down');\n"
            "\n"
            "      this.swipedCards.push({ index: this.currentIndex, action: 'down' });\n"
            "      this.lastAction = { action: 'down', cardIndex: this.currentIndex };\n"
            "\n"
            "      setTimeout(() => {\n"
            "        this.currentIndex++;\n"
            "        topCard.remove();\n"
            "        this.addNewCardToStack();\n"
            "        this.updateCardStackClasses();\n"
            "        this.updateSwipeCounter();\n"
            "        this.bindEvents();\n"
            "        if (this.currentIndex >= this.cards.length) {\n"
            "          this.render();\n"
            "        }\n"
            "        this.sendResults();\n"
            "        this.isAnimating = false;\n"
            "        updateFrameHeightDebounced();\n"
            "      }, 300);\n"
            "    }\n"
            "  }\n\n"
            "  goBack() {",
        ),
        (
            "      const directionClass =\n"
            "        lastSwiped.action === 'left' ? 'return-from-left' : 'return-from-right';\n"
            "      topCard.classList.add(directionClass);\n"
            "      setTimeout(() => {\n"
            "        topCard.classList.remove('return-from-left', 'return-from-right');\n"
            "        this.isAnimating = false;\n"
            "        updateFrameHeightDebounced();\n"
            "      }, 300);",
            "      const directionClass =\n"
            "        lastSwiped.action === 'left'\n"
            "          ? 'return-from-left'\n"
            "          : lastSwiped.action === 'down'\n"
            "            ? 'return-from-down'\n"
            "            : 'return-from-right';\n"
            "      topCard.classList.add(directionClass);\n"
            "      setTimeout(() => {\n"
            "        topCard.classList.remove('return-from-left', 'return-from-right', 'return-from-down');\n"
            "        this.isAnimating = false;\n"
            "        updateFrameHeightDebounced();\n"
            "      }, 300);",
        ),
    ]


def _css_append():
    return f"""

{_PATCH_MARKER}
.swipe-card.swiped-down {{
  transform: translateY(420px) rotate(6deg);
  opacity: 0;
}}

.return-from-down {{
  animation: return-from-down 0.3s ease-out;
}}

@keyframes return-from-down {{
  from {{
    transform: translateY(420px) rotate(6deg);
    opacity: 0;
  }}
  to {{
    transform: translateX(0) translateY(0) rotate(0);
    opacity: 1;
  }}
}}

.action-buttons {{
  width: 100% !important;
  max-width: 560px;
  display: flex !important;
  flex-wrap: nowrap !important;
  justify-content: center !important;
  align-items: center !important;
  gap: 8px;
  margin-top: 14px !important;
}}

.action-btn {{
  width: auto !important;
  min-width: 0;
  min-height: 98px !important;
  height: auto !important;
  border-radius: 20px !important;
  border: 1.5px solid #B7D7EF !important;
  background: rgba(228, 241, 255, 0.92) !important;
  color: #123F5E !important;
  box-shadow: 0 8px 20px rgba(18, 63, 94, 0.10) !important;
  padding: 10px 10px 12px;
  font-size: 14px !important;
  line-height: 1.15 !important;
  text-align: center !important;
  white-space: normal !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: flex-start !important;
  gap: 10px !important;
  overflow: hidden !important;
  letter-spacing: 0.02em;
}}

.fs-swipe-icon {{
  width: 64px;
  height: 40px;
  flex: 0 0 64px;
  display: inline-block;
  background-repeat: no-repeat;
  background-size: 130% auto;
  background-position: center;
}}

.fs-left {{
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNDAgOTAnPgogIDxyZWN0IHdpZHRoPScxNDAnIGhlaWdodD0nOTAnIGZpbGw9J25vbmUnLz4KICA8ZyBmaWxsPScjN0I4Nzk0Jz4KICAgIDxwYXRoIGQ9J00xNiA0NWwxNC0xMnY4aDEydjhIMzB2OHonLz4KICAgIDxwYXRoIGQ9J000MCA0NWwxMi0xMHY3aDEwdjZINTJ2N3onIG9wYWNpdHk9JzAuOCcvPgogIDwvZz4KICA8Y2lyY2xlIGN4PSc5MicgY3k9JzQ1JyByPScyNCcgZmlsbD0nI0Q4RUNGNycvPgogIDxwYXRoIGQ9J00xMDIgNDVIODRtMCAwbDctN20tNyA3bDcgNycgc3Ryb2tlPScjMEIzQTUyJyBzdHJva2Utd2lkdGg9JzQnIHN0cm9rZS1saW5lY2FwPSdyb3VuZCcgc3Ryb2tlLWxpbmVqb2luPSdyb3VuZCcgZmlsbD0nbm9uZScvPgo8L3N2Zz4=");
}}

.fs-right {{
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNDAgOTAnPgogIDxyZWN0IHdpZHRoPScxNDAnIGhlaWdodD0nOTAnIGZpbGw9J25vbmUnLz4KICA8ZyBmaWxsPScjN0I4Nzk0Jz4KICAgIDxwYXRoIGQ9J00xMjQgNDVsLTE0LTEydjhIOTh2OGgxMnY4eicvPgogICAgPHBhdGggZD0nTTEwMCA0NWwtMTItMTB2N0g3OHY2aDEwdjd6JyBvcGFjaXR5PScwLjgnLz4KICA8L2c+CiAgPGNpcmNsZSBjeD0nNDgnIGN5PSc0NScgcj0nMjQnIGZpbGw9JyNEOEVDRjcnLz4KICA8cGF0aCBkPSdNMzggNDVoMThtMCAwbC03LTdtNyA3bC03IDcnIHN0cm9rZT0nIzBCM0E1Micgc3Ryb2tlLXdpZHRoPSc0JyBzdHJva2UtbGluZWNhcD0ncm91bmQnIHN0cm9rZS1saW5lam9pbj0ncm91bmQnIGZpbGw9J25vbmUnLz4KPC9zdmc+");
}}

.fs-down {{
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNDAgOTAnPgogIDxyZWN0IHdpZHRoPScxNDAnIGhlaWdodD0nOTAnIGZpbGw9J25vbmUnLz4KICA8Y2lyY2xlIGN4PSc3MCcgY3k9JzI4JyByPScyMicgZmlsbD0nI0Q4RUNGNycvPgogIDxwYXRoIGQ9J003MCAxOHYxOG0wIDBsLTgtOG04IDhsOC04JyBzdHJva2U9JyMwQjNBNTInIHN0cm9rZS13aWR0aD0nNCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJyBzdHJva2UtbGluZWpvaW49J3JvdW5kJyBmaWxsPSdub25lJy8+CiAgPGcgZmlsbD0nIzdCODc5NCc+CiAgICA8cGF0aCBkPSdNNzAgNTBsLTEyLTEwaDh2LTZoOHY2aDh6Jy8+CiAgICA8cGF0aCBkPSdNNzAgNjZsLTEyLTEwaDh2LTZoOHY2aDh6JyBvcGFjaXR5PScwLjgnLz4KICA8L2c+Cjwvc3ZnPg==");
}}

.fs-back {{
  background-image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAxNDAgOTAnPgogIDxyZWN0IHdpZHRoPScxNDAnIGhlaWdodD0nOTAnIGZpbGw9J25vbmUnLz4KICA8Y2lyY2xlIGN4PSc3MCcgY3k9JzQ1JyByPScyNCcgZmlsbD0nI0Q4RUNGNycvPgogIDxwYXRoIGQ9J004NiA0NUg2MG0wIDBsOC04bS04IDhsOCA4JyBzdHJva2U9JyMwQjNBNTInIHN0cm9rZS13aWR0aD0nNCcgc3Ryb2tlLWxpbmVjYXA9J3JvdW5kJyBzdHJva2UtbGluZWpvaW49J3JvdW5kJyBmaWxsPSdub25lJy8+CiAgPHBhdGggZD0nTTk0IDMyYTIyIDIyIDAgMSAxLTIgMzAnIHN0cm9rZT0nIzdCODc5NCcgc3Ryb2tlLXdpZHRoPSc0JyBzdHJva2UtbGluZWNhcD0ncm91bmQnIGZpbGw9J25vbmUnLz4KPC9zdmc+");
}}

.fs-swipe-copy {{
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.05;
}}

.fs-swipe-copy b {{
  font-size: 14px;
  letter-spacing: 0.03em;
}}

.fs-swipe-copy small {{
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
}}

.btn-disagree,
.btn-pass,
.btn-like {{
  order: 1;
  flex: 1 1 calc(33.333% - 8px);
  max-width: 160px;
}}

.btn-back {{
  display: none !important;
}}

/* Fallback in case upstream back icon remains as orphan SVG */
.action-buttons > svg {{
  display: none !important;
}}

.btn-disagree {{
  background: rgba(228, 241, 255, 0.92) !important;
  border-color: #B7D7EF !important;
  color: #123F5E !important;
}}

.btn-like {{
  background: rgba(228, 241, 255, 0.92) !important;
  border-color: #B7D7EF !important;
  color: #123F5E !important;
}}

.btn-pass {{
  display: flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  background: rgba(228, 241, 255, 0.92) !important;
  border-color: #B7D7EF !important;
  color: #123F5E !important;
}}

/* If upstream and patch both render PASS, keep only one */
.action-buttons .btn-pass + .btn-pass {{
  display: none !important;
}}

.action-indicator {{
  font-size: 14px !important;
  line-height: 1.25 !important;
  text-align: center !important;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(183, 215, 239, 0.95);
  background: rgba(228, 241, 255, 0.90);
  color: #123F5E !important;
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
}}

.action-indicator .fs-swipe-icon {{
  filter: none;
  width: 46px;
  height: 30px;
  flex: 0 0 46px;
  background-size: 122% auto;
}}

.fs-ind-copy {{
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1.05;
}}

.fs-ind-copy b {{
  font-size: 13px;
  letter-spacing: 0.03em;
}}

.fs-ind-copy small {{
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}}

.action-indicator.like {{
  right: 16px;
  color: #123F5E !important;
}}

.action-indicator.pass {{
  left: 16px;
  color: #123F5E !important;
}}

.action-indicator.down {{
  left: 50%;
  transform: translate(-50%, 0);
  bottom: 16px;
  top: auto;
  color: #123F5E !important;
}}

/* Avoid top/bottom clipping of tall card images on mobile */
.cards-stack {{
  width: min(92vw, 520px) !important;
  height: min(92vw, 520px) !important;
  max-width: 520px !important;
  max-height: 520px !important;
  margin: 0 auto 8px auto !important;
}}

.swipe-card {{
  width: 100% !important;
  height: 100% !important;
}}

.swipe-card .card-image {{
  height: 100% !important;
  object-fit: contain !important;
  background: transparent !important;
  border-radius: 16px !important;
}}

.swipe-card .card-content {{
  display: none !important;
}}

@media (max-width: 480px) {{
  .action-buttons {{
    gap: 8px;
    margin-top: 18px !important;
  }}

  .action-btn {{
    min-height: 88px !important;
    padding: 9px 8px 10px;
  }}

  .fs-swipe-icon {{
    width: 56px;
    height: 35px;
    flex: 0 0 56px;
  }}

  .fs-swipe-copy b {{
    font-size: 13px;
  }}

  .fs-swipe-copy small {{
    font-size: 11px;
  }}

  .cards-stack {{
    width: min(94vw, 440px) !important;
    height: min(94vw, 440px) !important;
    max-width: 440px !important;
    max-height: 440px !important;
  }}
}}
"""


def _build_patched_frontend_dir(package_root: Path):
    source_frontend = package_root / "frontend"
    if not source_frontend.exists():
        return None

    base_temp = Path(tempfile.gettempdir()) / "fs_swipecards_patch_v29"
    target_frontend = base_temp / "frontend"

    if not target_frontend.exists():
        if base_temp.exists():
            shutil.rmtree(base_temp, ignore_errors=True)
        target_frontend.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_frontend, target_frontend, dirs_exist_ok=True)

    js_path = target_frontend / "main.js"
    css_path = target_frontend / "style.css"
    if not js_path.exists() or not css_path.exists():
        return None

    js = js_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")

    if _PATCH_MARKER not in js:
        js = _replace_all(js, _js_replacements())
        js += f"\n\n{_PATCH_MARKER}\n"
        js_path.write_text(js, encoding="utf-8")
    if _PATCH_MARKER not in css:
        css += _css_append()
        css_path.write_text(css, encoding="utf-8")

    return target_frontend


def load_streamlit_swipecards():
    try:
        import streamlit_swipecards as _sc
    except Exception:
        return None

    try:
        package_root = Path(_sc.__file__).resolve().parent
        patched_frontend = _build_patched_frontend_dir(package_root)
        if patched_frontend:
            _sc._component_func = components.declare_component(
                "streamlit_swipecards_fs_patch",
                path=str(patched_frontend),
            )
    except Exception:
        # Keep graceful fallback to original dependency.
        pass

    return _sc.streamlit_swipecards
