FROM alpine:3.22
RUN apk add --no-cache openssh-client
COPY apps/weekly_report_tunnel/entrypoint.sh /usr/local/bin/report-tunnel
ENTRYPOINT ["sh", "/usr/local/bin/report-tunnel"]
