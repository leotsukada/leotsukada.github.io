all: horizontal_line delete_watermark files/lt_logo.png

horizontal_line: index.html.bk
	sed -i -e 's@<strong>Leo Tsukada</strong><br></h1>@<strong>Leo Tsukada</strong><br><hr width="400pt" size="5"></h1>@g' index.html

delete_watermark: index.html.bk
	$(eval LINE := $(shell grep mobirise index.html -n | tail -n 1 |  cut -f1 -d:))
	sed -i -e '$(LINE)s@style=\"@style=\"display:none;@g' index.html

smaller_logo:index.html.bk 
sed -i -e "s@3.8rem@3.0rem@g" index.html
index.html.bk:
	cp index.html $@

clean:
	rm -f index.html.*