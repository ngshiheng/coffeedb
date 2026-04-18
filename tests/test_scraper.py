from coffeedb.scraper import scrape_detail, scrape_list

LIST_HTML = """
<html>
  <body>
    <div class='e-loop-item'>
      <h2>2</h2>
      <h1><a href='https://theworlds100bestcoffeeshops.com/locales/second-shop/'>Second Shop</a></h1>
      <p>Norway</p>
    </div>
    <div class='e-loop-item'>
      <h2>1</h2>
      <h1><a href='https://theworlds100bestcoffeeshops.com/locales/first-shop/'>First Shop</a></h1>
      <p>Japan</p>
    </div>
  </body>
</html>
"""


DETAIL_HTML = """
<html>
  <body>
    <div data-elementor-type='single-post'>
      <h1 class='elementor-heading-title'>First Shop</h1>
      <div class='e-parent'>
        <h2>Contact</h2>
        <p class='elementor-heading-title'>Tokyo</p>
        <p class='elementor-heading-title'>Japan</p>
        <p class='elementor-heading-title'>1 Chome-1 Tokyo, Japan</p>
        <p><a href='https://first.example.com'>Website</a></p>
        <p><a href='https://instagram.com/firstshop'>Instagram</a></p>
      </div>
      <div class='elementor-widget-theme-post-content'>
        <p>Specialty coffee and pastries.</p>
        <p>Open daily.</p>
      </div>
      <div class='elementor-carousel-image' style="background-image:url('/img/a.jpg')"></div>
      <div class='elementor-carousel-image'><img src='/img/b.jpg' /></div>
    </div>
  </body>
</html>
"""


def test_scrape_list_parses_rows_and_sorts_by_rank() -> None:
    rows = scrape_list("https://example.com/list", html=LIST_HTML)

    assert len(rows) == 2
    assert rows[0]["rank"] == 1
    assert rows[0]["name"] == "First Shop"
    assert rows[0]["slug"] == "first-shop"
    assert rows[0]["country"] == "Japan"


def test_scrape_detail_extracts_core_fields() -> None:
    detail = scrape_detail("https://example.com/locales/first-shop/", html=DETAIL_HTML)

    assert detail["name"] == "First Shop"
    assert detail["city"] == "Tokyo"
    assert detail["country"] == "Japan"
    assert detail["address"] == "1 Chome-1 Tokyo, Japan"
    assert detail["website"] == "https://first.example.com"
    assert detail["instagram"] == "https://instagram.com/firstshop"
    assert detail["description"] == "Specialty coffee and pastries.\n\nOpen daily."
    assert detail["image_urls"] == [
        "https://example.com/img/a.jpg",
        "https://example.com/img/b.jpg",
    ]
