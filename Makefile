all: horizontal_line delete_watermark

horizontal_line: index.html.bk
	sed -i -e 's@<strong>Leo Tsukada</strong>@<strong>Leo Tsukada</strong><br><hr width="32%" size="5">@g' index.html

delete_watermark: index.html.bk
	$(eval LINE := $(shell grep mobirise index.html -n | tail -n 1 |  cut -f1 -d:))
	sed -i -e '$(LINE)s@style=\"@style=\"display:none;@g' index.html

index.html.bk:
	cp index.html $@

clean:
	rm -f index.html.*