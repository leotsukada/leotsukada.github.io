delete_watermark: index.html.bk
	$(eval LINE := $(shell grep Mobirise index.html -n | tail -n 1 |  cut -f1 -d:))
	sed -i -e '$(LINE)s@style=\"@style=\"display:none;@g' index.html

index.html.bk:
	cp index.html $@