/// Single shard Client
use crate::pb::generate::v1::text_generation_service_client::TextGenerationServiceClient;
use crate::pb::generate::v1::*;
use crate::Result;
use tonic::transport::{Channel, Uri};
use tracing::*;

/// Text Generation Inference gRPC client
#[derive(Clone)]
pub struct Client {
    stub: TextGenerationServiceClient<Channel>,
}

impl Client {
    /// Returns a client connected to the given url
    pub async fn connect(uri: Uri) -> Result<Self> {
        let channel = Channel::builder(uri).connect().await?;

        Ok(Self {
            stub: TextGenerationServiceClient::new(channel),
        })
    }

    /// Returns a client connected to the given unix socket
    pub async fn connect_uds(path: String) -> Result<Self> {
        let channel = Channel::from_shared("http://[::]:50051".to_string())
            .unwrap()
            .connect_with_connector(tower::service_fn(move |_: Uri| {
                tokio::net::UnixStream::connect(path.clone())
            }))
            .await?;

        Ok(Self {
            stub: TextGenerationServiceClient::new(channel),
        })
    }

    /// Returns a list of uris or unix sockets of all shards
    #[instrument(skip(self))]
    pub async fn service_discovery(&mut self) -> Result<Vec<String>> {
        let request = tonic::Request::new(ServiceDiscoveryRequest {});
        let response = self
            .stub
            .service_discovery(request)
            .instrument(info_span!("service_discovery"))
            .await?;
        let urls = response
            .into_inner()
            .urls
            .into_iter()
            // Remove unix socket prefix
            .map(|url| match url.strip_prefix("unix://") {
                None => url,
                Some(stripped_url) => stripped_url.to_string(),
            })
            .collect();
        Ok(urls)
    }

    /// Clear the past generations cache
    #[instrument(skip(self))]
    pub async fn clear_cache(&mut self) -> Result<()> {
        let request = tonic::Request::new(ClearCacheRequest {});
        self.stub
            .clear_cache(request)
            .instrument(info_span!("clear_cache"))
            .await?;
        Ok(())
    }

    /// Generate one token for each request in the given batch
    ///
    /// Returns Generation for each request in batch
    /// and the next cached batch
    #[instrument(skip(self))]
    pub async fn prefill(&mut self, batch: Batch) -> Result<(Vec<Generation>, Option<Batch>)> {
        let request = tonic::Request::new(PrefillRequest { batch: Some(batch) });
        let response = self
            .stub
            .prefill(request)
            .instrument(info_span!("prefill"))
            .await?
            .into_inner();
        Ok((response.generations, response.batch))
    }

    /// Generate one token for each request in the given cached batches
    ///
    /// Returns Generation for each request in batches
    /// and the next cached batch
    #[instrument(skip(self))]
    pub async fn decode(
        &mut self,
        batches: Vec<Batch>,
    ) -> Result<(Vec<Generation>, Option<Batch>)> {
        let request = tonic::Request::new(DecodeRequest { batches });
        let response = self
            .stub
            .decode(request)
            .instrument(info_span!("decode"))
            .await?
            .into_inner();
        Ok((response.generations, response.batch))
    }
}
